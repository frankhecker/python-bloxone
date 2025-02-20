#!/usr/local/bin/python3
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
'''
------------------------------------------------------------------------

 Description:
    Simple utility functions for data type validation, domain handling,
    and data normalisationa specifically with the aim of supporting
    queries to TIDE and Dossier.

 Requirements:
   Python3 with re, ipaddress, requests 

 Author: Chris Marrison

 Date Last Updated: 20210224

 Todo:

 Copyright (c) 2018 Chris Marrison / Infoblox

 Redistribution and use in source and binary forms,
 with or without modification, are permitted provided
 that the following conditions are met:

 1. Redistributions of source code must retain the above copyright
 notice, this list of conditions and the following disclaimer.

 2. Redistributions in binary form must reproduce the above copyright
 notice, this list of conditions and the following disclaimer in the
 documentation and/or other materials provided with the distribution.

 THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
 FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
 COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
 INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
 BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
 LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
 CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
 LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
 ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 POSSIBILITY OF SUCH DAMAGE.

------------------------------------------------------------------------
'''
__version__ = '0.0.3'
__author__ = 'Chris Marrison'
__author_email__ = 'chris@infoblox.com'

import logging
import os
import re
import configparser
import datetime
import ipaddress
import requests
import urllib.parse
import sqlite3

# ** Global Vars **


# ** Data Validation functions ** #

def data_type(qdata, host_regex, url_regex):
    '''
    Validate and determine data type (host, ip or url)

    Parameters:
        qdata (str): data to determine type/validity
        host_regex/url_regex (re): pre-compiled regexes

    Returns:
        dtype (str): data type of qdata ("ip", "host", or "url")
    '''
    if validate_ip(qdata):
        dtype = "ip"
    elif validate_url(qdata, url_regex):
        dtype = "url"
    elif validate_fqdn(qdata, host_regex):
        dtype = "host"
    else:
        dtype = "invalid"
    return dtype


def buildregex():
    '''
    Pre-compile 'standard' regexes as used by data_type and
    validate_XXX functions

    Parameters:
        none

    Returns:
        host_regex (re): Compiled regex for hostnames
        url_regex (re): Compiled regex for URLs
    '''
    # Added _ for support of Microsoft domains
    host_regex = re.compile(r'(?!-)[A-Z\d\-\_]{1,63}(?<!-)$', re.IGNORECASE)
    url_regex = re.compile(
        # r'^(?:http|ftp)s?://' # http:// or https://
        # http:// or https://
        r'^(?:http)s?://'
        # domain...
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'
        # localhost...
        r'localhost|'
        # ...or ipv4
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|'
        # ...or ipv6
        r'\[?[A-F0-9]*:[A-F0-9:]+\]?)'
        # optional port
        r'(?::\d+)?'
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return host_regex, url_regex


def validate_fqdn(hostname, regex):
    '''
    Validate input data is a legitmate fqdn

    Parameters:
        hostname (str): fqdn as a string

    Returns:
        bool: Return True for valid and False otherwise

    '''
    if len(hostname) > 255 or len(hostname) < 1:
        result = False
    if hostname.endswith("."):
        # strip exactly one dot from the right, if present
        hostname = hostname[:-1]
    result = all(regex.match(x) for x in hostname.split("."))

    return result


def validate_ip(ip):
    '''
    Validate input data is a valid IP address

    Parameters:
        ip (str): ip address as a string

    Returns:
        bool: Return True for valid and False otherwise

    '''
    try:
        ipaddress.ip_address(ip)
        result = True
    except ValueError:
        result = False
    return result


def validate_url(url, regex):
    '''
    Validate input data is a valid URL

    Parameters:
        url (str): string to verify as URL
        regex (re): pre-compiled regex obj

    Returns:
        bool: Return True for valid and False otherwise

    '''
    result = regex.match(url)
    return result


# ** Misc Functions **

def reverse_labels(domain):
    '''
    Reserve order of domain labels (or any dot separated data, e.g. IP)

    Parameters:
        domain (str): domain.labels
    Returns:
        rdomain (str): labels.domain
    '''
    rdomain = ""
    labels = domain.split(".")
    for l in reversed(labels):
        if rdomain:
            rdomain = rdomain+"."+l
        else:
            rdomain = l
    return rdomain


# ** Data Conversion functions ** #

def convert_url_to_host(url):
    '''
    Break down URL and return host element

    Parameters:
        url (str): Validated URL

    Returns:
        host (str): hostname or ip

    '''
    # Break down URL and return host element
    componants = url.split("/")
    host = componants[2]

    # Remove port if present
    if ":" in host:
        componants = host.split(":")
        host = componants[0]

    return host


def normalise(item, itype=None, port=False, www=False):
    '''
    Take ip, host or url item process and
    return normalise data.

    Parameters:
        item (str): item to normalise
        itype (str): One of ["host", "url", "ip"]
        port (bool): stip port number e.g. :8080
        www (bool): strip www. from hostname

    Returns:
        normalised (str): Normalised item or "invalid"

    '''
    # Local varlables

    # Check for itype being set
    if not itype:
        # Build regexes for data_type checking
        host_regex, url_regex = buildregex()
        itype = data_type(item, host_regex, url_regex)

    if itype != "invalid":
        # Normalise item
        if itype == "url":
            # Parse URL
            parsed_url = urllib.parse.urlparse(item)
            # Strip unneeded elements (protocol, params, query, *port, *www)
            if port:
                item = parsed_url.hostname + parsed_url.path
            else:
                item = parsed_url.netloc + parsed_url.path

            # Remove www if required
            if www and item.startswith('www.'):
                item = item[4:]

        elif itype == "host":
            # Remove trailing dot if present
            if item.endswith("."):
                item = item[:-1]

            # Remove port if required
            if port and ":" in item:
                componants = item.split(":")
                item  = componants[0]

            # Remove www if required
            if www and item.startswith('www.'):
                item = item[4:]

            # Ensure lower case
            item = item.lower()

        elif itype == "ip":
            # Remove port if required
            if port and ":" in item:
                componants = item.split(":")
                item = componants[0]

        normalised = item

    else:
        normalised = itype

    return normalised


def count_labels(fqdn):
    '''
    Count number of labels in an FQDN

    Parameters:
        fqdn (str): Hostname as fqdn

    Returns:
        count (int): number of labels
    '''

    labels = []

    labels = fqdn.split(".")
    count = len(labels)

    return count


def strip_host(fqdn):
    '''
    Take FQDN and strip first label
    or fqdn if no. of labels is 2 or less

    Parameters:
        fqdn (str): Hostname as fqdn

    Returns:
        domain (str): stripped domain down to two labels
    '''
    labels = []
    domain = ""

    labels = fqdn.split(".")
    if len(labels) <= 2:
        domain = fqdn
    else:
        domain = get_domain(fqdn, no_of_labels=(len(labels) - 1))
        '''
        Alternate code with get_domain

        host = labels.pop(0)
        for label in labels:
            domain += label
            domain += "."
        domain = domain.rstrip(".")
        '''

    return domain


def get_domain(fqdn, no_of_labels=2):
    '''
    Take FQDN and return n label domain
    or fqdn if no. of labels is 2 or less

    Parameters:
        fqdn (str): Hostname as fqdn
        no_of_labels (int): Number of labels to return
            default = 2

    Returns:
        domain (str): N label domain name or fqdn

    '''

    # Local variables
    labels = []
    domain = ""
    count = 0

    labels = fqdn.split(".")
    count = len(labels)

    if count <= no_of_labels:
        domain = fqdn
    else:
        for label in range((count - no_of_labels), (count)):
            domain += labels[label]
            domain += "." 
        # Strip last "."
        domain = domain.rstrip(".")

    return domain

# ** Local db Functions **

def opendb(dbfile):
    '''
    Open sqlite db and return cursor()

    Parameters:
        dbfile (str): path to file

    Returns:
        cursor (obj): Returns a db.cursor()
    '''
    if os.path.isfile(dbfile):
        db = sqlite3.connect(dbfile)
        db.row_factory = sqlite3.Row
        cursor = db.cursor()
    else:
        logging.error("Database "+dbfile+" not found.")
        cursor = None

    return cursor


def get_table(cursor):
    '''
    Determine db table and return

    Parameters:
        cursor (obj): db.cursor object

    Returns:
        table (str): Table name as string
    '''
    # ** Determine table name ** #
    select = 'SELECT name FROM sqlite_master WHERE type="table"'
    cursor.execute(select)
    tables = cursor.fetchall()
    # ** Expecting single table ** #
    if len(tables) == 1:
        # ** Assume table is correct (even if it isn't) ** #
        table = tables[0][0]
    else:
        # ** Print error and exit ###
        logging.error("DB not of correct format - too many tables")
        table = None

    return table


def db_query(db_cursor, table, query_type, query_data, *flags):
    '''
    Perform db query and return appropriate rows

    Parameters:
        db_cursor (obj): db.cursor object
        table (str): database table name
        query_type (str): data type for query
        query_data (str): search string

    Returns:
        rows (list): (All matching db rows
    '''
    if query_type == "host":
        # ** Form DB Query **
        select = ('SELECT * FROM '
                  + table + ' WHERE host="' + query_data
                  + '" OR domain="' + query_data+'"')
        # Ignore class = "Policy"
        if flags:
            select = select+' AND property!="Policy_UnsolictedBulkEmail"'
    elif query_type == "ip":
        # ** Form DB Query **
        select = 'SELECT * FROM '+table+' WHERE ip="'+query_data+'"'
        # Ignore class = "Policy"
        if flags:
            select = select+' AND property!="Policy_UnsolictedBulkEmail"'
    elif query_type == "url":
        # ** Form DB Query **
        select = 'SELECT * FROM '+table+' WHERE url="'+query_data+'"'
        # Ignore class = "Policy"
        if flags:
            select = select+' AND property!="Policy_UnsolictedBulkEmail"'
    else:
        logging.error("Invalid Type for {} data type for {}"
                      " - should not be here".format(query_type, query_data))
        return None

    db_cursor.execute(select)
    rows = db_cursor.fetchall()

    return rows
