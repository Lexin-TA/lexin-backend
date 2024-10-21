from datetime import datetime

from sqlmodel import SQLModel


# Data model used for requests/responses in the application.
# Legal document model for indexing to and from elasticsearch
class LegalDocumentBase(SQLModel):
    # Concise mappings.
    title: str
    jenis_bentuk_peraturan: str
    pemrakarsa: str
    nomor: int
    tahun: int
    tentang: str
    tempat_penetapan: str
    ditetapkan_tanggal: str | None
    status: str

    # Extra mappings.
    dasar_hukum: list[str]

    mengubah: list[str]
    diubah_oleh: list[str]
    mencabut: list[str]
    dicabut_oleh: list[str]

    melaksanakan_amanat_peraturan: list[str]
    dilaksanakan_oleh_peraturan_pelaksana: list[str]

    filenames: list[str]
    resource_urls: list[str]
    reference_urls: list[str]

    content: list[str]


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
            "nomor": {"type": "integer"},
            "tahun": {"type": "integer"},
            "tentang": {"type": "text"},
            "tempat_penetapan": {"type": "keyword"},
            "ditetapkan_tanggal": {"type": "date", "format": "dd-MM-yyyy"},
            "status": {"type": "keyword"},

            # Extra mappings.
            "dasar_hukum": {"type": "text"},    # This is an array of strings.

            "mengubah": {"type": "text"},       # This is an array of strings.
            "diubah_oleh": {"type": "text"},    # This is an array of strings.
            "mencabut": {"type": "text"},       # This is an array of strings.
            "dicabut_oleh": {"type": "text"},   # This is an array of strings.

            "melaksanakan_amanat_peraturan": {"type": "text"},          # This is an array of strings.
            "dilaksanakan_oleh_peraturan_pelaksana": {"type": "text"},  # This is an array of strings.

            "filenames": {"type": "keyword"},       # This is an array of strings.
            "resource_urls": {"type": "text"},      # This is an array of strings.
            "reference_urls": {"type": "text"},     # This is an array of strings.

            "content": {"type": "text"},            # This is an array of strings.
        }
    }
}
