"""Clearing Agent became a master (Link) on Shipping Document / Customs Clearance: create records for existing values."""

from nsa_import.patches.create_port_and_vessel_masters import execute as _execute


def execute():
	_execute()
