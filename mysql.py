import pymysql
from pymysql.converters import escape_string


class MySQLDatabase():
    """
    Whenever sending a SQL to MySQL server, use conn_acquire and conn_release to 
    establish and close a new connection exclusively used for this SQL execution.
    This can avoid waiting timeout problem caused by MySQL's default setting.
    """
    DB_HOST = '192.168.17.1'

    def __init__(self, in_product=True):
        self.mysql_conn = None
        if in_product:
            self.DB_PORT = 23306
        else:
            self.DB_PORT = 23307
    
    def conn_acquire(self):
        self.mysql_conn = pymysql.connect(host=self.DB_HOST, port=self.DB_PORT, user='ki3-backends', 
                                         password='Backends12345@', db='website')

        # # set max_allowed_packet to 1G
        # with self.mysql_conn.cursor() as cursor:
        #     cursor.execute('set global max_allowed_packet=1073741824;')
        # self.mysql_conn.commit()
    
    def conn_release(self):
        self.mysql_conn.close()
        
    def executes(self,sqls):
        """
        Execute the given sql.
        """

        self.conn_acquire()

        try:
            with self.mysql_conn.cursor() as cursor:
                for sql in sqls:
                    cursor.execute(sql)
            self.mysql_conn.commit()
        except Exception as e:
            try:
                self.mysql_conn.rollback()
            except Exception:
                pass
            self.conn_release()
            return False, '[ERROR] {}'.format(str(e))

        self.conn_release()
        return True, None

    def execute(self, sql):
        """
        Execute the given sql.
        """

        self.conn_acquire()

        try:
            with self.mysql_conn.cursor() as cursor:
                cursor.execute(sql)
            self.mysql_conn.commit()
        except Exception as e:
            try:
                self.mysql_conn.rollback()
            except Exception:
                pass
            self.conn_release()
            return False, '[ERROR] {}'.format(str(e))
        
        self.conn_release()
        return True, None
    
    def fetch(self, sql):
        """
        Execute the given sql and fetch results from db.
        """

        self.conn_acquire()

        select_results = set()
        try:
            with self.mysql_conn.cursor() as cursor:
                cursor.execute(sql)
                select_results = cursor.fetchall()
        except Exception as e:
            self.conn_release()
            return False, '[ERROR] {}'.format(str(e))

        self.conn_release()
        return True, select_results
    
    def get_column_names(self, table):
        """
        Get column names of the given table.
        """

        column_list = list()
        query_sql = ("SELECT COLUMN_NAME "
                     "FROM information_schema.COLUMNS "
                     "WHERE table_schema='website' AND table_name='{}'".format(table))
        
        _, resp = self.fetch(query_sql)
        for tuple in resp:
            column_list.append(tuple[0])
        
        return column_list
    
    def single_insert(self, table, res_list, col_list=None,is_replace=False):
        return self.batch_insert(table, [res_list,], col_list,is_replace)

    def batch_insert(self, table, res_list, col_list=None,is_replace=False):
        if is_replace:
            return self.batch_insert_with_mode(table,res_list,col_list=col_list,mode='replace')
        else:
            return self.batch_insert_with_mode(table,res_list,col_list=col_list,mode='append')

    def batch_insert_with_mode(self, table, res_list, col_list=None,mode='append'):
        """

        Insert batch records to db
        
        :param table:       the name of table to perform INSERT
        :param res_list:    the 2d list of VALUES to INSERT
        :param col_list:    the list of column names to perform INSERT
                            None if all columns are used

        # append insert into语义(可能会插入报错)
        # replace replace into 语义
        # redo 先delete全表，然后重新插入
        """

        if len(res_list) == 0:
            return True, None

        # Construct INSERT SQL sentences.
        if col_list is None:
            attr_str = ''
        else:
            attr_str = '({})'.format(','.join(col_list))
        if mode in ['append','redo']:
            sql = "INSERT INTO {} {} VALUES".format(table, attr_str)
        elif mode in ['replace']:
            sql = "REPLACE INTO {} {} VALUES".format(table, attr_str)
        else:
            pass
        value_pattern = "("
        for attr in res_list[0]:
            if type(attr) in [int, float, bool]:
                value_pattern += "{},"
            else:
                value_pattern += "'{}',"
        value_pattern = value_pattern[:-1] + '),'

        for res in res_list:
            my_res = [escape_string(v) if isinstance(v,str) else v for v in res]
            sql += value_pattern.format(*my_res)
        sql = sql[:-1] + ';'
        # may not be safe
        sql = sql.replace(',None',',NULL')
        if mode=='redo':
            sqls = ['delete from {}'.format(table),sql]
            return self.executes(sqls)
        else:
            return self.execute(sql)
    
    def batch_delete(self, table, res_list, col_name):
        """
        Delete records from db multiple values of one column.

        :param table:       the name of table to perform DELETE
        :param res_list:    the 1d list values of column to DELETE
        :param col_name:    the column to define WHERE to DELETE
        """

        if len(res_list) == 0:
            return True, None

        # construct DELETE SQL sentences.
        sql = "DELETE FROM {} WHERE ".format(table)

        if type(res_list[0]) == int:
            condition_pattern = col_name + " = {}"
        else:
            condition_pattern = col_name + " = '{}'"
        
        sql += ' OR '.join([condition_pattern.format(res) for res in res_list]) + ';'
        
        return self.execute(sql)
    
    def dump(self, table):
        """
        Dump the given table's data.
        """
        dump_sql = "DELETE FROM {};".format(table)
        return self.execute(dump_sql)
    def truncate(self,table):
        truncate_sql = "truncate {};".format(table)
        return self.execute(truncate_sql)

