# tools/rv32iss.py
"""Instruction decode adapter for the RV32I ISS."""

if __package__:
	from .rv32enc import decode_mnemonic, fields
else:
	from rv32enc import decode_mnemonic, fields


def decode_instruction(word):
	"""Return the shared mnemonic and fields, or None for an illegal word."""
	mnemonic = decode_mnemonic(word)
	if mnemonic is None:
		return None
	return mnemonic, fields(word)