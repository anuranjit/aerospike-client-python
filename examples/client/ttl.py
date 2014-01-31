#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

# Test the TTL feature for the Aerospike Server.
# We will write records that expire BEFORE the default namespace TTL,
# we will write records that expire with the default TTL, and we'll
# write records that NEVER expire.
#
# NOTE:
# This test is meant to run on an Aerospike 2.x or 3.x server, so the
# records that it writes have only primitive types for bin values.

import aerospike
import sys
import textwrap
import time

from optparse import OptionParser

################################################################################
# Option Parsing
################################################################################

usage = "usage: %prog [options]"

optparser = OptionParser(usage=usage, add_help_option=False)

optparser.add_option(
  "--help", dest="help", action="store_true",
  help="Displays this message.")

optparser.add_option(
  "-h", "--host", dest="host", type="string", default="127.0.0.1", metavar="<ADDRESS>",
  help="Address of Aerospike server.")

optparser.add_option(
  "-p", "--port", dest="port", type="int", default=3000, metavar="<PORT>",
  help="Port of the Aerospike server.")

optparser.add_option(
  "-n", "--namespace", dest="namespace", type="string", default="test", metavar="<NS>",
  help="Port of the Aerospike server.")

optparser.add_option(
  "-s", "--set", dest="set", type="string", default="demo", metavar="<SET>",
  help="Port of the Aerospike server.")



(options, args) = optparser.parse_args()

if options.help:
  optparser.print_help()
  print()
  sys.exit(1)

################################################################################
# CONSTANTS
################################################################################

TTL_DEFAULT = 10
TTL_MAX = 20
TTL_NO_EXPIRE = -1


# Define the Namespace Supervisor parms -- setting the period very short
# so that we know it will have visited all of our records before we look
# at them at each TTL interval.
PARAMS_SERVICE = [[ ('nsup-period', 1) ]]

# Define the default Namespace Time To Live at 10 seconds. We will write
# some records that expire EARLY (5 seconds), some records that expire at
# the default (10 seconds), some that expire LATE (15 seconds) and some
# that NEVER expire.
# We set MAX ttl to 20 to check that our flag (0xFFFFFFFF) is allowed in
# and does not trigger the "greater than max ttl" warning.
# Also, we'll check that one of our records DOES trigger the Max TTL warning
# with a TTL of greater than 20.
PARAMS_NAMESPACE = [[ ('default-ttl',TTL_DEFAULT), ('max-ttl',TTL_MAX) ]]

# Write Policy names and related values
AS_POLICY_W_TIMEOUT   = "timeout"

AS_POLICY_W_RETRY     = "retry"
AS_POLICY_RETRY_UNDEF = 0 # Use Default value
AS_POLICY_RETRY_NONE  = 1 # No retry
AS_POLICY_RETRY_ONCE  = 2 # Retry Once

AS_POLICY_W_KEY        = "key"
AS_POLICY_KEY_UNDEF    = 0 # If set, then the value will default to either
                           # as_config.policies.key or `AS_POLICY_KEY_DEFAULT`.
AS_POLICY_KEY_DIGEST   = 1 # Send the digest value of the key.
AS_POLICY_KEY_SEND     = 2 # Send the key, but do not store it.
AS_POLICY_KEY_STORE    = 3 # Store the key (NOT YET IMPLEMENTED)

AS_POLICY_W_GEN        = "generation"
AS_POLICY_GEN_UNDEF    = 0 # Use default value
AS_POLICY_GEN_IGNORE   = 1 # Write a record, regardless of generation.
AS_POLICY_GEN_EQ       = 2 # Write a record, ONLY if generations are equal 
AS_POLICY_GEN_GT       = 3 # Write a record, ONLY if local generation is 
                           # greater-than remote generation.
AS_POLICY_GEN_DUP      = 4 # Write a record creating a duplicate, ONLY if
                           # the generation collides (?)

AS_POLICY_W_EXISTS     = "exists"
AS_POLICY_EXISTS_UNDEF = 0 # Use default value
AS_POLICY_EXISTS_IGNORE= 1 # Write the record, regardless of existence.
AS_POLICY_EXISTS_CREATE= 2 # Create a record, ONLY if it doesn't exist.
AS_POLICY_EXISTS_UPDATE= 3 # Update a record, ONLY if it exist (NOT YET IMPL).

# Setup write policy
wr_policy = {
    AS_POLICY_W_TIMEOUT: 5000,
    AS_POLICY_W_RETRY:   AS_POLICY_RETRY_NONE,
    AS_POLICY_W_KEY:     AS_POLICY_KEY_DIGEST,
    AS_POLICY_W_GEN:     AS_POLICY_GEN_IGNORE,
    AS_POLICY_W_EXISTS:  AS_POLICY_EXISTS_IGNORE
}

BASE_KEY_RANGE = range(1,11)

SPECIAL_KEYS = {
  20: { 'ttl': 5,
        'desc': '5 sec TTL' },
  40: { 'ttl': 15,
        'desc': '15 sec TTL' },
  60: { 'ttl': TTL_NO_EXPIRE,
        'desc': 'NO_EXPIRE TTL' },
  80: { 'ttl': TTL_MAX+1,
        'desc': 'Larger than MAX TTL' }
}

KEYS = BASE_KEY_RANGE + SPECIAL_KEYS.keys()

################################################################################
# Connect to Cluster
################################################################################

config = {
  'hosts': [ (options.host, options.port) ]
}

print('Connect to Server: %s', config)
client = aerospike.client(config).connect()

################################################################################
# Perform Operation
################################################################################


def test_params_for_stanza(p,contx,is_namespace):
  for t in p:
    if is_namespace:
      info_code = "set-config:context=namespace;id="+contx+";"+t[0]+"="+str(t[1])
    else:
      info_code = "set-config:context="+contx+";"+t[0]+"="+str(t[1])
    try:
      v = client.info(info_code).items()
      res = v[0][1][1]
      if res!="ok\n":
        print("setting {0} to {1} failed. Got result({2})".format(t[0],t[1],res))
        sys.exit(1)
      else:
        print("setting {0} to {1} succeeded".format(t[0],t[1]))
    except:
        print("error: info_code({0}) result({1})".format(info_code,v))

def print_header(header,message=None):
  print()
  print(''.ljust(80,'='))
  print(header)
  print(message) if message else None
  print(''.ljust(80,'-'))

def print_record((key, meta, record), prefix=''):
  print("%s%-4d %-4s %-8s %s" % (
    prefix,
    key['key'], 
    meta.get('gen') if meta and 'gen' in meta else '-', 
    meta.get('ttl') if meta and 'ttl' in meta else '-', 
    record if record else '-'
  ))

def print_records(records, prefix=''):
  header = "%s---- ---- -------- " % prefix
  header = header.ljust(80,'-')
  print()
  print("%s%-4s %-4s %-8s %s" % (prefix, "key", "gen", "ttl", "record"))
  print(header)
  [print_record(r, prefix) for r in records]

def print_histogram(prefix=''):
  request = ''.join(["hist-dump:ns=",options.namespace,";hist=ttl"])

  header = "%sHISTOGRAM (%s)" % (prefix,request)
  border = prefix.ljust(80,'-')

  print()
  print(header)
  print(border)
  for node,(error,response) in client.info(request).items():
    if error:
      print('%serror: %s' % (prefix, error))
    else:
      for line in textwrap.wrap(response,80-len(prefix)):
        print("%s%s" % (prefix,line))


def check_records(start, wait=0, message=None):

  if wait:
    time.sleep(wait)

  n = options.namespace
  s = options.set

  stop = time.time()
  duration = int(stop - start)

  print_header('CHECK :: wait=%s duration=%s' % (wait, duration), message)

  try:
    print_records([client.key(n, s, k).get() for k in KEYS],'  ')
  except Exception as e:
    print("error: {0}".format(e), file=sys.stderr)
    sys.exit(1)

  print_histogram('  ')

def delete_records():
  try:
    for key in KEYS:
      # first remove the existing record
      client.key(options.namespace, options.set, key).remove()
  except Exception as e:
    print("error: {0}".format(e), file=sys.stderr)
    sys.exit(1)

def write_records():
  try:
    for key in KEYS:
      ttl = SPECIAL_KEYS[key]['ttl'] if key in SPECIAL_KEYS else None

      rec = {}
      rec['key'] = key
      rec['ttl'] = ttl if ttl else TTL_DEFAULT
      rec['desc'] = SPECIAL_KEYS[key]['desc'] if key in SPECIAL_KEYS else 'default TTL'

      try:
        # write a new record
        # ttl=None is equivalent to not setting a ttl
        client.key(options.namespace, options.set, key).put(rec, {'ttl':ttl})

      except Exception as e:
        if ttl > TTL_MAX:
          print('error: (correct) failed to write record with TTL(%d) > TTL_MAX(%d)' % (ttl, TTL_MAX))
        else:
          print('error: failed to write record with TTL = %d' % ttl)

  except Exception as e:
    print("error: {0}".format(e), file=sys.stderr)
    sys.exit(1)

################################################################################
# CONFIGURE SERVER
################################################################################

print_header("CONFIGURE THE SERVER")

# Now go off and set the params
print('Set Parameters for Service')
for p in PARAMS_SERVICE:
    test_params_for_stanza(p,"service",False)
    time.sleep(1)
print("service parameters passed")

print('Set Parameters for Namespace')
for p in PARAMS_NAMESPACE:        
    test_params_for_stanza(p,options.namespace,True)
    time.sleep(1)
print("namespace parameters passed")

################################################################################
# CHECK RECORDS ON INTERVALS
################################################################################

start = time.time()

delete_records()
check_records(start, 0, 'Clean state')
write_records()
check_records(start, 0, 'Initial state')
check_records(start, 2, 'Expect all records with TTL-2')
check_records(start, 6, 'Expect all records with TTL<=5 to be gone')
check_records(start, 3, 'Expect all records with TTL<=10 to be gone')
check_records(start, 6, 'Expect all records to be gone, except NO_EXPIRE')
