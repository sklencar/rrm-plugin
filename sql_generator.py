
"""
comments for triggers - to store attribute mapping

COMMENT ON TRIGGER dsp_trg_1_source_trigger ON test_dsp_source IS 'test comment sourceX';

SELECT obj_description( (SELECT oid FROM pg_trigger WHERE tgname='dsp_trg_1_source_trigger'), 'pg_trigger');
"""

import json

# global configuration for prefixes of stored functions and triggers
prefix_fcn = 'dsp_fcn'
prefix_trg = 'dsp_trg'


def parse_trigger_name(trigger_name):
    """ Returns tuple (trigger_id, is_source) from trigger's name """
    x = trigger_name[len(prefix_trg) + 1:]  # chop off the prefix and underscore
    trigger_id_str = x[:x.index('_')]  # chop off the right side
    trigger_id = int(trigger_id_str)
    is_source = trigger_name.endswith('_source_trigger')
    return (trigger_id, is_source)


def list_triggers(conn):
    cur = conn.cursor()
    sources = {}  # key = trigger ID, value = source table name
    targets = {}  # key = trigger ID, value = target table name
    cur.execute("""SELECT tgname, relname, nspname FROM pg_trigger
        LEFT JOIN pg_class ON tgrelid = pg_class.oid
        LEFT JOIN pg_namespace nsp ON relnamespace = nsp.oid
        WHERE tgname LIKE '%s%%'""" % prefix_trg)
    for row in cur.fetchall():
        (trigger_id, is_source) = parse_trigger_name(row[0])
        table_name = row[1]
        schema_name = row[2]
        if is_source:
            sources[trigger_id] = schema_name + "." + table_name
        else:
            targets[trigger_id] = schema_name + "." + table_name

    lst = []
    for trigger_id in sources:
        src = sources[trigger_id]
        trg = targets[trigger_id] if trigger_id in targets else None
        lst.append((trigger_id, src, trg))

    diff = set(targets.keys()) - set(sources.keys())
    for trigger_id in diff:
        if trigger_id not in targets: continue
        src = sources[trigger_id] if trigger_id in sources else None
        trg = targets[trigger_id]
        lst.append((trigger_id, src, trg))
    return lst


class SqlGenerator:
    """ Class to generate SQL for our triggers """
    
    source_table = 'public.test_dsp_source'
    target_table = 'public.test_dsp_target'
    trg_fcn_id = 1
    attr_map = { 'attr_int': 'attr_int1', 'attr_text': 'attr_text1' }  # source to target mapping
    
    def drop_sql(self):
        return """
        DROP TRIGGER IF EXISTS %(prefix_trg)s_%(trg_fcn_id)d_source_trigger ON %(source_table)s cascade;
        DROP FUNCTION IF EXISTS %(prefix_fcn)s_%(trg_fcn_id)d_source_trigger() cascade;
        DROP TRIGGER IF EXISTS %(prefix_trg)s_%(trg_fcn_id)d_target_trigger ON %(target_table)s cascade;
        DROP FUNCTION IF EXISTS %(prefix_fcn)s_%(trg_fcn_id)d_target_trigger() cascade;
        """ % {
            'source_table': self.source_table,
            'target_table': self.target_table,
            'prefix_fcn': prefix_fcn,
            'prefix_trg': prefix_trg,
            'trg_fcn_id': self.trg_fcn_id,
            }

    def create_sql(self):
        
        first_target_attr = self.attr_map.values()[0]
        
        assignments_null = []
        assignments_copy = []
        for source_attr, target_attr in self.attr_map.iteritems():
            assignments_null.append("NEW.%s = NULL;" % target_attr)
            assignments_copy.append("NEW.%s = myrec.%s;" % (target_attr, source_attr))
            
        return """
        -- trigger to watch changes in the source table
        CREATE OR REPLACE FUNCTION %(prefix_fcn)s_%(trg_fcn_id)d_source_trigger() RETURNS TRIGGER AS $$
        DECLARE
            bbox geometry;
        BEGIN
        IF (TG_OP = 'DELETE') THEN
            bbox := OLD.geom;
        ELSIF (TG_OP = 'INSERT') THEN
            bbox := NEW.geom;
        ELSE  -- update
            bbox := st_envelope(st_union(st_envelope(OLD.geom), st_envelope(NEW.geom)));
        END IF;
        
        -- trigger update of target layer
        UPDATE %(target_table)s SET %(first_target_attr)s = NULL WHERE geom && bbox;
        
        RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;

        -- TODO: better performance - for the whole table just once?
        DROP TRIGGER IF EXISTS %(prefix_trg)s_%(trg_fcn_id)d_source_trigger ON %(source_table)s;
        CREATE TRIGGER %(prefix_trg)s_%(trg_fcn_id)d_source_trigger
        AFTER INSERT OR UPDATE OR DELETE ON %(source_table)s
            FOR EACH ROW EXECUTE PROCEDURE %(prefix_fcn)s_%(trg_fcn_id)d_source_trigger();

        -- trigger on the target table to actually update the data
        CREATE OR REPLACE FUNCTION %(prefix_fcn)s_%(trg_fcn_id)d_target_trigger() RETURNS TRIGGER AS $$
        DECLARE
        myrec RECORD;
            BEGIN
                -- using dwithin to account for numerical issues when dealing with linestrings
                -- set to 1cm tolerance (assuming CRS in meters)
                SELECT * INTO myrec FROM %(source_table)s src WHERE st_dwithin(NEW.geom, src.geom, 0.01);
                IF NOT FOUND THEN
                  %(assignments_null)s
                ELSE
                  %(assignments_copy)s
                END IF;
                RETURN NEW;
            END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS %(prefix_trg)s_%(trg_fcn_id)d_target_trigger ON %(target_table)s;

        CREATE TRIGGER %(prefix_trg)s_%(trg_fcn_id)d_target_trigger
        BEFORE INSERT OR UPDATE ON %(target_table)s
            FOR EACH ROW EXECUTE PROCEDURE %(prefix_fcn)s_%(trg_fcn_id)d_target_trigger();

        COMMENT ON TRIGGER %(prefix_trg)s_%(trg_fcn_id)d_target_trigger ON %(target_table)s IS '%(json)s';

        """ % {
            'source_table': self.source_table,
            'target_table': self.target_table,
            'prefix_fcn': prefix_fcn,
            'prefix_trg': prefix_trg,
            'trg_fcn_id': self.trg_fcn_id,
            'first_target_attr': first_target_attr,
            'assignments_null': "\n".join(assignments_null),
            'assignments_copy': "\n".join(assignments_copy),
            'json': self.write_json().replace("'", "\\'")
            }

    def load_trigger_sql(self):
        """Gets trigger definition stored in JSON from target table's comments"""
        return """SELECT obj_description( (SELECT oid FROM pg_trigger WHERE tgname='%(prefix_trg)s_%(trg_fcn_id)d_target_trigger'), 'pg_trigger');""" % {
            'prefix_trg': prefix_trg,
            'trg_fcn_id': self.trg_fcn_id,
        }

    def parse_json(self, json_str):
        """Parse JSON document and set up the class or raise ValueError on errors"""
        data = json.loads(json_str)
        self.source_table = data['source_table']
        self.target_table = data['target_table']
        self.trg_fcn_id = data['trg_fcn_id']
        self.attr_map = data['attr_map']

    def write_json(self):
        """Returns string with trigger data encoded in JSON document"""
        data = {
            'source_table': self.source_table,
            'target_table': self.target_table,
            'trg_fcn_id': self.trg_fcn_id,
            'attr_map': self.attr_map,
        }
        return json.dumps(data)
