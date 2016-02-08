#!/usr/local/bin/python3
"""
OS X script to decrypt CoreStorage Volumes.

Inspired by Unlock (https://github.com/jridgewell/Unlock).
"""

import sys
import pathlib
import json
import os
import stat
import subprocess
import argparse
import getpass

passwords_path = "/Library/PrivilegedHelperTools/Generated_Files/com.juanjonol.unlock.json"


def main(argv=None):
	if not sys.platform == 'darwin':
		raise NotImplementedError("This program only works in OS X")

	args = parse_args(argv)

	if args.subcommand == "add":
		add_disk(disk=args.disk, uuid=args.uuid, password=args.password)

	elif args.subcommand == "delete":
		delete_disk(disk=args.disk, uuid=args.uuid, password=args.password)

	elif args.subcommand == "replace":
		replace_value(old_value=args.old, new_value=args.new)

	elif args.subcommand == "uuid":
		get_uuid(disk=args.disk)

	else:
		decrypt_disks()


# Parse the arguments given by the user.
def parse_args(argv):

	parser = argparse.ArgumentParser(description="Decrypt CoreStorage volumes.")
	parser.add_argument('--version', action='version', version='1.0.0')
	subparsers = parser.add_subparsers(dest="subcommand")  # Store the used subcommand in the "subcommand" attribute

	execute_description = "Decrypt the disks whose UUID and password has been saved."
	subparsers.add_parser("execute", help=execute_description, description=execute_description)

	add_description = "Saves the UUID and password of a disk."
	add_command = subparsers.add_parser("add", help=add_description, description=add_description)
	path_or_uuid_group = add_command.add_mutually_exclusive_group()
	path_or_uuid_group.add_argument("-d", "--disk", help="Path to the disk, in the form \"/dev/diskN\".")
	path_or_uuid_group.add_argument("-u", "--uuid", help="UUID of the disk.")
	add_command.add_argument("-p", "--password", help="Password of the disk.")

	delete_description = "Deletes the UUID and password of a disk."
	delete_command = subparsers.add_parser("delete", help=delete_description, description=delete_description)
	path_or_uuid_group = delete_command.add_mutually_exclusive_group()
	path_or_uuid_group.add_argument("-d", "--disk", help="Path to the disk, in the form \"/dev/diskN\".")
	path_or_uuid_group.add_argument("-u", "--uuid", help="UUID of the disk.")
	delete_command.add_argument("-p", "--password", help="Password of the disk.")

	replace_description = "Replaces a value (UUID or password)."
	replace_command = subparsers.add_parser("replace", help=replace_description, description=replace_description)
	replace_command.add_argument("-o", "--old", help="Old value to replace.")
	replace_command.add_argument("-n", "--new", help="New value.")

	uuid_description = "Returns the CoreStorage UUID of a volume."
	uuid_command = subparsers.add_parser("uuid", help=uuid_description, description=uuid_description)
	uuid_command.add_argument("-d", "--disk", help="Path to the disk.")

	return parser.parse_args()


# Decrypts the disks saved
def decrypt_disks():
	# Gets the JSON (or, if it doesn't exists, an empty list)
	data = get_json(passwords_path)

	# Decrypts all disks
	for dictionary in data:
		for uuid in dictionary.keys():
			password = dictionary[uuid]

			# Decrypt each disk
			subprocess.run(["diskutil", "coreStorage", "unlockVolume", uuid, "-passphrase", password], check=True)

			# Mount each disk
			subprocess.run(["diskutil", "mount",  uuid], check=True)


# Tests and saves an UUID and password, to latter decrypt
def add_disk(disk=None, uuid=None, password=None):
	# If the user is not root, give a warning
	if os.getuid() != 0:
		print("WARNING: The current user is not root. It's recommended that only root has access to the passwords.")

	# If the UUID or the password haven't been passed as arguments, request it.
	if uuid is None:
		if disk is None:
			disk = input("Introduce the path to the disk to unlock (in the form \"/dev/disk/\"):")
		uuid = get_uuid(disk)

	if password is None:
		password = getpass.getpass("Introduce password: ")

	# Gets the JSON (or, if it doesn't exists, an empty list)
	data = get_json(passwords_path)

	# Checks if the UUID is already added to the JSON
	for dictionary in data:
		if uuid in dictionary.keys():
			print(
				"The UUID is already added to the JSON. Use \"decrypt-disk -r\" if you want to replace the UUID or the password.")
			return

	# TODO: Test UUID and password before saving it

	# Update the data in the JSON
	data.append({uuid: password})
	write_json_secure(data, passwords_path)
	print("Added disk with UUID", uuid)


# Deletes a UUID and his corresponding password
def delete_disk(disk=None, uuid=None, password=None):
	# If the UUID or the password haven't been passed as arguments, request it.
	if uuid is None:
		if disk is None:
			disk = input("Introduce the path to the disk to unlock (in the form \"/dev/disk/\"):")
		uuid = get_uuid(disk)

	if password is None:
		password = getpass.getpass("Introduce password: ")

	# Gets the JSON (or, if it doesn't exists, an empty list)
	data = get_json(passwords_path)

	# Checks if the UUID is already added to the JSON
	for dictionary in data:
		if uuid in dictionary.keys():
			# Deletes the UUID
			data.remove({uuid: password})  # This just works if the uuid and the password match.
			os.remove(passwords_path)  # This shouldn't be needed (the file should be destroyed when writing in it).
			write_json_secure(data, passwords_path)
			print("Deleted disk with UUID ", uuid)
			return

	# If the program reach this point, the UUID wasn't in the passwords file.
	print("The UUID is not saved, or the password of that UUID is incorrect.")


# Replaces a UUID or password.
def replace_value(old_value=None, new_value=None):
	# If the old or the new value haven't been passed as arguments, request it.
	if old_value is None:
		old_value = input("Introduce old value: ")

	if new_value is None:
		new_value = input("Introduce new value: ")

	# Gets the JSON (or, if it doesn't exists, an empty list)
	data = get_json(passwords_path)

	for dictionary in data:
		for uuid in dictionary.keys():
			password = dictionary[uuid]
			if uuid == old_value or password == old_value:
				delete_disk(uuid, password)
				add_disk(new_value, password)
				print("Replaced value", old_value, "with value", new_value)
				return

	# It the program reach this point, the old_value wasn't in the file.
	print("The value given is not saved, so it can't be replaced.")

	
# Returns the UUID for a CoreStorage volume
def get_uuid(disk=None):
	# If the path hasn't been passed as argument, request it.
	if disk is None:
		disk = input("Introduce the path to the disk to unlock (in the form \"/dev/disk/\"):")

	try:
		command = ["diskutil", "coreStorage", "information", disk]
		result = subprocess.run(command, stdout=subprocess.PIPE, check=True).stdout.decode("utf-8")
	except subprocess.CalledProcessError:
		print("The given path is not from a CoreStorage disk.")

	# Parse the UUID from the CoreStorage information
	info_list = result.splitlines()
	uuid_line = info_list[2]
	uuid_line_splitted = uuid_line.split(" ")
	uuid = uuid_line_splitted[len(uuid_line_splitted)-1]  # The UUID is the last element in the UUID line
	print(uuid)
	return uuid


# Returns the JSON string in the file on the given path, or an empty list if there isn't a file
def get_json(file_path):
	path = pathlib.Path(file_path)
	if path.is_file():
		try:
			with open(file_path, "r") as input:
				return json.loads(input.read())
		except json.JSONDecodeError:
			return []
	else:
		return []


# Writes a list as a JSON, in a file that can be read and write just for the current user.
def write_json_secure(data, file_path):

	folder_permissions = stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR # 0o700: Read, write and execute just for the current user
	file_permissions = stat.S_IRUSR | stat.S_IWUSR  # 0o600: Read and write just for the current user

	# If the folder where the files go doesn't exists, create it
	path = pathlib.Path(file_path)
	if not path.parent.is_dir():
		path.parent.mkdir(folder_permissions)

	# Saves the JSON
	with os.fdopen(os.open(file_path, os.O_WRONLY | os.O_CREAT, file_permissions), 'w') as output:
		print(json.dumps(data), file=output)


if __name__ == '__main__':
	sys.exit(main(sys.argv))
