"""Battlezone II PAK reader and extractor."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass


MAGIC = b"DOCP"


class PakFormatError(Exception):
	pass


@dataclass(frozen=True)
class PakEntry:
	directory_index: int
	name: str
	offset: int
	size: int

	def archive_path(self, directories):
		if 0 <= self.directory_index < len(directories):
			directory = directories[self.directory_index]
			if directory:
				return directory + "\\" + self.name
		return self.name


def _read_u8(data, offset):
	return data[offset], offset + 1


def _read_u32_le(data, offset):
	return int.from_bytes(data[offset:offset + 4], "little"), offset + 4


def _safe_relpath(pak_path):
	normalized = pak_path.replace("/", "\\").strip("\\")
	parts = [part for part in normalized.split("\\") if part and part != "."]
	if any(part == ".." for part in parts):
		raise PakFormatError("Archive path contains parent traversal")
	return os.path.join(*parts) if parts else ""


class PakArchive:
	def __init__(self, filepath, directories, entries):
		self.filepath = filepath
		self.directories = directories
		self.entries = entries
		self.entries_by_path = {
			entry.archive_path(self.directories): entry for entry in entries
		}

	@classmethod
	def read(cls, filepath):
		with open(filepath, "rb") as f:
			header = f.read(24)
			if len(header) < 24 or header[:4] != MAGIC:
				raise PakFormatError("Invalid Battlezone II PAK header")

			version = int.from_bytes(header[4:8], "little")
			directory_count = int.from_bytes(header[8:12], "little")
			directory_offset = int.from_bytes(header[12:16], "little")
			file_count = int.from_bytes(header[16:20], "little")
			file_table_offset = int.from_bytes(header[20:24], "little")

			if version != 1:
				raise PakFormatError(f"Unsupported PAK version {version}")

			data = f.read()
			data = header + data

		if directory_offset > len(data) or file_table_offset > len(data):
			raise PakFormatError("PAK table offsets exceed file size")

		offset = directory_offset
		directories = []
		for _ in range(directory_count):
			length, offset = _read_u8(data, offset)
			directory = data[offset:offset + length].decode("ascii")
			offset += length
			directories.append(directory)

		offset = file_table_offset
		entries = []
		for _ in range(file_count):
			directory_index, offset = _read_u32_le(data, offset)
			name_length, offset = _read_u8(data, offset)
			name = data[offset:offset + name_length].decode("ascii")
			offset += name_length
			file_offset, offset = _read_u32_le(data, offset)
			size, offset = _read_u32_le(data, offset)
			entries.append(PakEntry(directory_index, name, file_offset, size))

		return cls(filepath, directories, entries)

	def list_paths(self, extension=None):
		paths = [entry.archive_path(self.directories) for entry in self.entries]
		if extension:
			extension = extension.casefold()
			paths = [path for path in paths if path.casefold().endswith(extension)]
		return paths

	def resolve_entry(self, archive_path):
		normalized = archive_path.replace("/", "\\").strip("\\")
		if normalized in self.entries_by_path:
			return self.entries_by_path[normalized]

		lower = normalized.casefold()
		matches = [
			entry for path, entry in self.entries_by_path.items()
			if path.casefold() == lower or entry.name.casefold() == lower
		]
		if len(matches) == 1:
			return matches[0]
		if not matches:
			raise PakFormatError(f"Archive entry not found: {archive_path}")
		raise PakFormatError(f"Archive path is ambiguous: {archive_path}")

	def extract_entry(self, archive_path, output_root, overwrite=False):
		entry = self.resolve_entry(archive_path)
		relative_path = _safe_relpath(entry.archive_path(self.directories))
		output_path = os.path.join(output_root, relative_path)
		os.makedirs(os.path.dirname(output_path), exist_ok=True)

		if overwrite or not os.path.exists(output_path) or os.path.getsize(output_path) != entry.size:
			with open(self.filepath, "rb") as source:
				source.seek(entry.offset)
				payload = source.read(entry.size)
			with open(output_path, "wb") as dest:
				dest.write(payload)

		return output_path

	def extract_all(self, output_root, overwrite=False):
		output_paths = []
		with open(self.filepath, "rb") as source:
			for entry in self.entries:
				relative_path = _safe_relpath(entry.archive_path(self.directories))
				output_path = os.path.join(output_root, relative_path)
				parent = os.path.dirname(output_path)
				if parent:
					os.makedirs(parent, exist_ok=True)

				if overwrite or not os.path.exists(output_path) or os.path.getsize(output_path) != entry.size:
					source.seek(entry.offset)
					payload = source.read(entry.size)
					with open(output_path, "wb") as dest:
						dest.write(payload)

				output_paths.append(output_path)

		return output_paths


def default_cache_dir(pak_filepath):
	stat = os.stat(pak_filepath)
	cache_key = f"{os.path.basename(pak_filepath)}_{stat.st_size}_{int(stat.st_mtime)}"
	return os.path.join(tempfile.gettempdir(), "io_scene_bz2xsi", "pak_cache", cache_key)


def ensure_extracted(pak_filepath, output_root=None):
	if output_root is None:
		output_root = default_cache_dir(pak_filepath)

	archive = PakArchive.read(pak_filepath)
	marker = os.path.join(output_root, ".io_scene_bz2xsi_pak_complete")
	expected_marker = f"{os.path.getsize(pak_filepath)}:{int(os.path.getmtime(pak_filepath))}"

	if not os.path.exists(marker) or open(marker, "r", encoding="utf8").read().strip() != expected_marker:
		os.makedirs(output_root, exist_ok=True)
		archive.extract_all(output_root, overwrite=True)
		with open(marker, "w", encoding="utf8") as f:
			f.write(expected_marker)

	return archive, output_root
