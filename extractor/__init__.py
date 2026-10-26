"""Regex extraction of players and coaches from the saved nhl.com pages.

The extract_* functions take HTML strings and return dicts; they do no file
I/O, so they can later be mapped over the pages in Spark.
"""
