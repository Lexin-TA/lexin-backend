from datetime import datetime

from sqlmodel import SQLModel


# Data model used for requests/responses in the application.
# Legal document model for indexing to and from elasticsearch
class LegalDocumentBase(SQLModel):
    # Concise mappings.
    id: str
    title: str
    jenis_bentuk_peraturan: str
    pemrakarsa: str
    nomor: str
    tahun: int
    tentang: str
    tempat_penetapan: str
    ditetapkan_tanggal: str | None
    pejabat_yang_menetapkan: str
    status: str

    # Extra mappings.
    tahun_pengundangan: int | None
    tanggal_pengundangan: str | None
    nomor_pengundangan: int | None
    nomor_tambahan: int | None
    pejabat_pengundangan: str | None

    dasar_hukum: list[dict[str, str]]

    mengubah: list[dict[str, str]]
    diubah_oleh: list[dict[str, str]]
    mencabut: list[dict[str, str]]
    dicabut_oleh: list[dict[str, str]]

    melaksanakan_amanat_peraturan: list[dict[str, str]]
    dilaksanakan_oleh_peraturan_pelaksana: list[dict[str, str]]

    filenames: list[str]
    resource_urls: list[str]
    reference_urls: list[str]

    content_type: list[list[str]]
    content_text: list[list[str]]


class LegalDocumentCreate(LegalDocumentBase):
    pass


class LegalDocumentRead(LegalDocumentBase):
    pass


# Elasticsearch mappings used for initial index creation of legal documents.
ELASTICSEARCH_LEGAL_DOCUMENT_MAPPINGS = {
    "mappings": {
        "properties": {
            # Concise mappings.
            "title": {"type": "text"},
            "jenis_bentuk_peraturan": {"type": "keyword"},
            "pemrakarsa": {"type": "keyword"},
            "nomor": {"type": "keyword"},
            "tahun": {"type": "integer"},
            "tentang": {"type": "text"},
            "tempat_penetapan": {"type": "keyword"},
            "ditetapkan_tanggal": {"type": "date", "format": "dd-MM-yyyy"},
            "pejabat_yang_menetapkan": {"type": "keyword"},
            "status": {"type": "keyword"},

            # Extra mappings.
            "tahun_pengundangan": {"type": "integer"},
            "tanggal_pengundangan": {"type": "date", "format": "dd-MM-yyyy"},
            "nomor_pengundangan": {"type": "integer"},
            "nomor_tambahan": {"type": "integer"},
            "pejabat_pengundangan": {"type": "keyword"},

            "dasar_hukum": {
                "type": "nested",
                "properties": {
                    "id": {"type": "text"},
                    "title": {"type": "text"},
                }
            },

            "mengubah": {
                "type": "nested",
                "properties": {
                    "id": {"type": "text"},
                    "title": {"type": "text"},
                }
            },
            "diubah_oleh": {
                "type": "nested",
                "properties": {
                    "id": {"type": "text"},
                    "title": {"type": "text"},
                }
            },
            "mencabut": {
                "type": "nested",
                "properties": {
                    "id": {"type": "text"},
                    "title": {"type": "text"},
                }
            },
            "dicabut_oleh": {
                "type": "nested",
                "properties": {
                    "id": {"type": "text"},
                    "title": {"type": "text"},
                }
            },

            "melaksanakan_amanat_peraturan": {
                "type": "nested",
                "properties": {
                    "id": {"type": "text"},
                    "title": {"type": "text"},
                }
            },
            "dilaksanakan_oleh_peraturan_pelaksana": {
                "type": "nested",
                "properties": {
                    "id": {"type": "text"},
                    "title": {"type": "text"},
                }
            },

            "filenames": {"type": "text"},          # This is an array of strings.
            "resource_urls": {"type": "text"},      # This is an array of strings.
            "reference_urls": {"type": "text"},     # This is an array of strings.

            "content_type": {"type": "keyword"},    # This is an array of strings.
            "content_text": {"type": "text"},       # This is an array of strings.

        }
    }
}
