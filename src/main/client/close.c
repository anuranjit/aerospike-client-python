/*******************************************************************************
 * Copyright 2013-2016 Aerospike, Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 ******************************************************************************/

#include <Python.h>

#include <aerospike/aerospike.h>
#include <aerospike/as_error.h>

#include "client.h"
#include "conversions.h"
#include "exceptions.h"
#include "global_hosts.h"

#define MAX_PORT_SIZE 6

/**
 *******************************************************************************************************
 * Closes already opened connection to the database.
 *
 * @param self                  AerospikeClient object
 * @param args                  The args is a tuple object containing an argument
 *                              list passed from Python to a C function
 * @param kwds                  Dictionary of keywords
 *
 * Returns None.
 * In case of error,appropriate exceptions will be raised.
 *******************************************************************************************************
 */
PyObject * AerospikeClient_Close(AerospikeClient * self, PyObject * args, PyObject * kwds)
{
	as_error err;
	char *alias_to_search = NULL;

	// Initialize error
	as_error_init(&err);

	if (!self || !self->as) {
		as_error_update(&err, AEROSPIKE_ERR_PARAM, "Invalid aerospike object");
		goto CLEANUP;
	}

	alias_to_search = return_search_string(self->as);
	PyObject *py_persistent_item = NULL;

	py_persistent_item = PyDict_GetItemString(py_global_hosts, alias_to_search); 
	if (py_persistent_item) {
		close_aerospike_object(self->as, &err, alias_to_search, py_persistent_item);
	} else {
		aerospike_close(self->as, &err);

		for (unsigned int i = 0; i < self->as->config.hosts_size; i++) {
			free((void *) self->as->config.hosts[i].addr);
		}

		Py_BEGIN_ALLOW_THREADS
		aerospike_destroy(self->as);
		Py_END_ALLOW_THREADS
	}
	self->is_conn_16 = false;
	self->as = NULL;
	PyMem_Free(alias_to_search);
	alias_to_search = NULL;

	Py_INCREF(Py_None);

CLEANUP:
	if ( err.code != AEROSPIKE_OK ) {
		PyObject * py_err = NULL;
		error_to_pyobject(&err, &py_err);
		PyObject *exception_type = raise_exception(&err);
		PyErr_SetObject(exception_type, py_err);
		Py_DECREF(py_err);
		return NULL;
	}
	return Py_None;
}

char* return_search_string(aerospike *as)
{
	char port_str[MAX_PORT_SIZE];

	int tot_address_size = 0;
	int tot_port_size = 0;
	int delimiter_size = 0;
	int i =0;
	//Calculate total size for search string
	for (i = 0; i < (int)as->config.hosts_size; i++)
	{
		tot_address_size = tot_address_size + strlen(as->config.hosts[i].addr);
		tot_port_size = tot_port_size + MAX_PORT_SIZE;
		delimiter_size = delimiter_size + 3;
	}

	char* alias_to_search = (char*) PyMem_Malloc(tot_address_size + strlen(as->config.user) + tot_port_size + delimiter_size);

	//Create search string
	strcpy(alias_to_search, as->config.hosts[0].addr);
	int port = as->config.hosts[0].port;
	sprintf(port_str, "%d", port);
	strcat(alias_to_search, ":");
	strcat(alias_to_search, port_str);
	strcat(alias_to_search, ":");
	strcat(alias_to_search, as->config.user);
	strcat(alias_to_search, ";");

	for (i = 1; i < (int)as->config.hosts_size; i++) {
		port = as->config.hosts[i].port;
		sprintf(port_str, "%d", port);
		strcat(alias_to_search, as->config.hosts[i].addr);
		strcat(alias_to_search, ":");
		strcat(alias_to_search, port_str);
		strcat(alias_to_search, ":");
		strcat(alias_to_search, as->config.user);
		strcat(alias_to_search, ";");
	}

	return alias_to_search;
}

void close_aerospike_object(aerospike *as, as_error *err, char *alias_to_search, PyObject *py_persistent_item)
{
		if (((AerospikeGlobalHosts*)py_persistent_item)->ref_cnt == 1) {
			PyDict_DelItemString(py_global_hosts, alias_to_search);
			AerospikeGlobalHosts_Del(py_persistent_item);
			aerospike_close(as, err);

			/*
			* Need to free memory allocated to host address string
			* in AerospikeClient_Type_Init.
			*/
			for( int i = 0; i < (int)as->config.hosts_size; i++) {
				free((void *) as->config.hosts[i].addr);
			}

			Py_BEGIN_ALLOW_THREADS
			aerospike_destroy(as);
			Py_END_ALLOW_THREADS
		} else {
			((AerospikeGlobalHosts*)py_persistent_item)->ref_cnt--;
		}
}
