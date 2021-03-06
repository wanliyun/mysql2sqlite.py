#!/usr/bin/env python
# coding: utf-8 -*-
from __future__ import print_function
#-------------------------------------------------------------------------------
# Name:		mysql2sqlite
# Purpose:	 Convert a mysql database to a sqlite database
#
# Author:	  Averell7 on SourceForge.net
#
# Created:	 6/01/2015
# Licence:	 GNU
#-------------------------------------------------------------------------------


"""
	This script will extract all data from a mysql database and create a corresponding sqlite database.
	It includes : Tables and their data
				  Indexes
				  Foreign Key constraints


	Usage :	 Edit the file mysql2sqlite.txt and indicate :
					your mysql parameters (host, database, login , password)
					your sqlite filename.

				Run the script.

"""

import sys
import traceback
import os.path
import re
try :
	import configparser	 # Python 3
	from configparser import ConfigParser, RawConfigParser
except :
	from ConfigParser import ConfigParser, RawConfigParser

import _mysql
import MySQLdb
from MySQLdb import cursors

import sqlite3 as sqlite


# ######### PARAMETERS #####################

myconfig = ConfigParser()

myconfig.read("mysql2sqlite.ini")

	

host=myconfig.get("mysql", "host")
user = myconfig.get("mysql", "user")
passwd = myconfig.get("mysql", "passwd")
database = myconfig.get("mysql", "database")


# sqlite database
delete_existing_file = myconfig.getint("sqlite", "delete_existing_file")
sqlite_file = myconfig.get("sqlite", "sqlite_file")



def sqlite_db_structure(logfile) :

	f1 = logfile
	table_def= {}


	req= "select name from sqlite_master where type in ('table')"
	cursor2.execute(req)
	result = cursor2.fetchall()
	for a in result :
		for b in a :
			table_def[b] = {}
			req = "PRAGMA table_info (" + b + ")"
			cursor2.execute(req)
			for s in cursor2 :
				table_def[b][s[1]] = s[2]



	return (table_def, {})		  # Index table is not yet supported


def mysql_db_structure(logfile) :

	table_def = {}
	index_def = {}
	constraint_def = {}
	errors_count = 0
	f1 = logfile

	# Extract mysql structure
	# Extract tables list
	cursor.execute("show tables")

	tables = []
	for row in cursor :
		key = row.keys()[0]
		name = row[key]
		try :
			cursor.execute("show columns from " + name)   # Test the validity of the table name.
														  # We have seen a database with a table named "1" which was impossible to handle with sql commands
			tables.append(name)
		except :
			print ("WARNING : Unable to handle table " + name + "\nCheck if there is no problem with it.")


	for name in tables :


		table_def[name] = {}
		index_def[name] = {}

		# extract columns
		cursor.execute("show columns from " + name)
		columns = cursor.fetchall()
		for col in columns :
			keys = col.keys()
			colname = col['Field']
			table_def[name][colname] = {}
			table_def[name][colname]['type'] = col['Type']
			table_def[name][colname]['null'] = col['Null']
			table_def[name][colname]['primary'] = col['Key']
			table_def[name][colname]['default'] = col['Default']
			table_def[name][colname]['autoinc'] = col['Extra']

		# Extract indexes
		cursor.execute("show indexes from " + name)
		columns = cursor.fetchall()
		for col in columns :
			keys = col.keys()
			colname = col['Key_name']
			if not colname in index_def[name] :
				index_def[name][colname] = {}
			index_def[name][colname]['non_unique'] = col['Non_unique']
			if 'column' in index_def[name][colname] :	   # indexes can work on multiple columns
				index_def[name][colname]['column'].append(col['Column_name'])
			else :
				index_def[name][colname]['column'] = [col['Column_name']]
			index_def[name][colname]['null'] = col['Null']


	# Extract foreign keys
	for table in table_def :
		cursor.execute("show create table " + table)
		result = cursor.fetchone()
		if not result:
			continue
		fkc = re.findall("FOREIGN.*?\n", result['Create Table'])
		if len(fkc) > 0 :
			constraint_def[table] = {}
			constraint_def[table] = " ".join(fkc)

	# Log structure

	# log table structure
	f1.write("Host = %s\nDatabase = %s \n\n" %(host,database))
	f1.write("Parameters are listed in the order : Type, Null Accepted, Primary Key, Auto increment, Default Value\n\n")
	for key in table_def :
		table = table_def[key]
		f1.write(key + "\n")
		for key2 in table :
			col = table[key2]
			data = "		 " + key2
			data += "   => " + chr(9) + col['type'] + ", " + col['null'] + ", "
			data += col['primary'] + ", " + col['autoinc']
			if col['default'] == None :
				data += ", NULL\n"
			else :
				data += ", " + col['default'] + "\n"
			f1.write(data)

	# Log indexes
	f1.write("\n\n=======================================================================\n\n")
	f1.write("Indexes list : \n\n")
	f1.write("Parameters are listed in the order : Column, Non_unique, Null\n\n")
	for key in index_def :
		index = index_def[key]
		f1.write(key + "\n")
		for key2 in index :
			col = index[key2]
			data = "		 " + key2
			data += "   => " + chr(9) + str(col['column']) + ", " + str(col['non_unique']) + ", " + col['null'] + "\n"
			f1.write(data)

	# Log Foreign Key Constraints
	f1.write("\n\n=======================================================================\n\n")
	f1.write("Foreign Key Constraints : \n\n")

	for key in constraint_def :
		f1.write(key + "\n")
		f1.write(constraint_def[key] + "\n")

	return(table_def, index_def, constraint_def)

def convert_mysql_to_sqlite() :


	f1 = open("mysql-sqlite.log", "w")
	errors_count = 0

	# Extract structure
	(table_def, index_def, constraint_def) = mysql_db_structure(f1)

	# Create sqlite database and tables
	type_errors = ""
	f1.write("\n\n====================================================\n\n")
	f1.write("Sqlite database creation\n\n")


	for key in table_def :

		# check if primary is single or multiple
		primary = []
	primary2=[]
		for col in table_def[key] :
			if table_def[key][col]['primary'] == "PRI" :
				primary.append(col)
		primary2.append("[" + col + "]")
		primary_count = len(primary)

		requete = "CREATE TABLE IF NOT EXISTS [" + key + "] ("		# table
		coldefs = []
		for col in table_def[key] :

			req = "\n[" + col + "] "				 # column name

			# Select the type
			type_s = table_def[key][col]['type']	# type
			type_s = type_s.lower().strip()
			if type_s in ["text", "integer", "boolean", "date"] :
				sqlite_type = type_s
			elif type_s in ["longtext", "mediumtext"] :
				sqlite_type = "text"
			elif type_s[0:7] in ["mediumi", "smallin", "tinyint"] :
				sqlite_type = "integer"
			elif type_s[0:3] in"int" :
				sqlite_type = "integer"
			elif type_s[0:7] == "varchar" :				 # TODO : affiner avec reg ?
				sqlite_type = type_s
			elif type_s[0:4] == "char" :					# TODO : affiner avec reg ?
				sqlite_type = "var" + type_s				# TODO : type sqlite ??
			else :
				type_errors += "\ntype error : " + type_s + "; set to varchar"
				sqlite_type = "varchar"
			# types non traités :  enum('moines','moniales','moines et moniales')

			# NULL
			null_s = table_def[key][col]['null']
			if null_s == "NO" :
				sqlite_null = " NOT NULL "
			else :
				sqlite_null = " NULL "

			# Key
			key_s = table_def[key][col]['primary']
			if key_s == "PRI" and primary_count == 1 :
				sqlite_key = " PRIMARY KEY "
			else :
				sqlite_key = ""

			# Default
			default_s = table_def[key][col]['default']
			if default_s :
				if isinstance(default_s, str) :
					sqlite_default = " DEFAULT '" + default_s + "' "
			else :
				sqlite_default = ""

			req += sqlite_type + sqlite_null + sqlite_key + sqlite_default
			coldefs.append(req)

		if primary_count > 1 :
			columns = ",".join(primary2)
			req = "\nCONSTRAINT prim PRIMARY KEY (" + columns + ")"
			coldefs.append(req)

		if key in constraint_def :
			coldefs.append("\n" + constraint_def[key])

		requete += ",".join(coldefs) + ")"


		f1.write(requete +"\n\n")

		#print requete
		try :
			cursor2.execute(requete)
		except :
			print ("Error :", requete)	 # TODO
	f1.write(type_errors)
	f1.close()
	cnx.commit()


	# populate tables

	i = 0
	for table in table_def :
		print ("\n" + table)
		# Extract data from mysql table
		req =  "select * from " + table
		cursor.execute(req)
		data = cursor.fetchall()
	if len(data) == 0:
		continue
		fields = data[0].keys()	   # extract field names

		# write in sqlite table
		header = "insert or ignore into " + table + " ("
		
	fields_list = []
	for a in fields:
		fields_list.append( "`" + a + "`")
	header += ",".join(fields_list)

	#fields_list = fields[0]
		#for a in fields[1:] :
		#	fields_list += ", " + a
		header += ") VALUES ("
		#header += fields_list
		for line in data :
			values = ""
			for field in fields :
				value = line[field]
				if value == None :
					value = "NULL"
				elif isinstance(value, str) :
					value = value.replace("'", "''")	  # escape quotes
					value = "'" + value + "'"
				values += str(value) + ", "
			values = values[:-2] + ")"	  # remove last comma and add parenthesis

			req = header + values

			try :
				cursor2.execute(req)
			except :
				print (req)
				printExcept2()
				errors_count += 1
				if errors_count > 10 :
					sys.exit()


			i += 1
			if i % 100 == 0 :
				sys.stdout.write(".")
				sys.stdout.flush()


		cnx.commit()


	# create indexes
	print ("\n")
	for table in index_def :
		for index1 in index_def[table] :
			if index1 == "PRIMARY" :
				continue				# primary indexes are alreay created
			data1 = index_def[table][index1]
			columns = data1['column']
			column = "[" + columns[0] + "]"
			if len(columns) > 1 :
				for i in range(1, len(columns)) :
					column += ", [" + columns[i] + "]"
			non_unique = data1['non_unique']
			is_null = data1['null']
			if non_unique == 0 :
				unique = "UNIQUE"
			else :
				unique = ""
			query = "CREATE %s INDEX [%s] ON [%s](%s);" % (unique, (table + "_" + index1), table, column)
			print (query)
			cursor2.execute(query)
			cnx.commit()


def printExcept2(
		  ) :
	a,b,c = sys.exc_info()
	for d in traceback.format_exception(a,b,c) :
		print (d,)
# ============================================================================


# open mysql database


link = MySQLdb.connect(host=host,user=user,passwd=passwd, db=database, cursorclass=cursors.DictCursor);
#link = MySQLdb.connect(host="192.168.1.4",user="dysmas",passwd="", db="maggy", cursorclass=cursors.DictCursor);
cursor = link.cursor()

cursor.execute("set character set utf8");
cursor.execute("set names utf8");

# create or open sqlite file

if delete_existing_file == True :
	if os.path.isfile(sqlite_file) :
		os.remove(sqlite_file)


cnx = sqlite.connect(sqlite_file)
# optimize performances
cnx.isolation_level = "DEFERRED"
# optimized transaction
cnx.isolation_level = "DEFERRED"
# ascii by default
cnx.text_factory = str
# access row fields by name
cnx.row_factory = sqlite.Row
cursor2 = cnx.cursor()

cursor2.execute("select sqlite_version()")
result = cursor2.fetchone()
print ("\nSqlite version : ", result[0], "\n")

convert_mysql_to_sqlite()
print ("\n\nConversion terminated.\nSee the full structure of the database in the mysql-sqlite.log file. ")
#convert_sqlite_to_mysql()


cnx.close()
