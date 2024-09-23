from sqlmodel import SQLModel


# Data model used for requests/responses in the application.
# Legal document model for indexing to and from elasticsearch
class LegalDocumentBase(SQLModel):
    title: str
    jenis_bentuk_peraturan: str
    pemrakarsa: str
    nomor: int
    tahun: int
    tentang: str
    tempat_penetapan: str
    ditetapkan_tanggal: str
    status: str

    filename: str
    content: str
    resource_url: str
    reference_url: str


class LegalDocumentCreate(LegalDocumentBase):
    pass


class LegalDocumentRead(LegalDocumentBase):
    str: int


# Elasticsearch mappings used for initial index creation of legal documents.
ELASTICSEARCH_LEGAL_DOCUMENT_MAPPINGS = {
    "mappings": {
        "properties": {
            "title": {"type": "text"},
            "jenis_bentuk_peraturan": {"type": "text"},
            "pemrakarsa": {"type": "text"},
            "nomor": {"type": "integer"},
            "tahun": {"type": "integer"},
            "tentang": {"type": "text"},
            "tempat_penetapan": {"type": "text"},
            "ditetapkan_tanggal": {"type": "text"},
            "status": {"type": "text"},

            "filename": {"type": "keyword"},
            "content": {"type": "text"},
            "resource_url": {"type": "text"},
            "reference_url": {"type": "text"}
        }
    }
}
