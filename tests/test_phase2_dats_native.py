from laclaugpt_data_analysis.dats_adapter import import_project
from laclaugpt_data_analysis.interoperability import (
    export_dats_csv_tables,
    import_dats_csv_tables,
)


def test_real_dats_csv_headers_map_to_canonical_project():
    tables = {
        "document_export_data.csv": (
            "filename,name,doctype,status,folder_name,folder_parent_name,tags,"
            "word_frequencies,metadata,content,html,raw_html,token_starts,token_ends,"
            "sentence_starts,sentence_ends,token_time_starts,token_time_ends,"
            "document_embedding,image_embedding,sentence_embeddings\n"
            "doc1.txt,Doc 1,text,1,LaclauGPT,,[],[],[],AI changes institutions.,,,[],[],"
            "[],[],,,,,[]\n"
        ),
        "project_1_all_codes.csv": (
            "code_name,description,color,parent_code_name\n"
            "AI,Artificial intelligence,,\n"
            "change,Change claims,,AI\n"
        ),
        "project_1_all_span_annotations.csv": (
            "uuid,sdoc_name,user_email,code_name,text,text_begin_char,text_end_char,"
            "text_begin_token,text_end_token,user_first_name,user_last_name\n"
            "ann-1,doc1.txt,researcher@example.org,change,AI,0,2,0,0,,\n"
        ),
        "project_1_all_memos.csv": (
            "uuid,user_email,favorited_by,title,icon,content,content_json,"
            "attached_type,attached_to\n"
            'memo-1,researcher@example.org,[],note,,Research memo,"{""text"": ""Research memo""}",'
            "project,project\n"
        ),
    }

    payload = import_dats_csv_tables(tables)
    project = import_project(payload)

    assert project.documents[0].content.text == "AI changes institutions."
    assert project.codes[1].parent_id == "dats-code:AI"
    assert project.annotations[0].code_id == "dats-code:change"
    assert project.annotations[0].producer.id == "researcher@example.org"
    assert project.notes[0].text == "Research memo"


def test_dats_csv_export_uses_upstream_schema_names():
    payload = import_dats_csv_tables(
        {
            "docs.csv": (
                "filename,name,doctype,status,folder_name,folder_parent_name,tags,"
                "word_frequencies,metadata,content,html,raw_html,token_starts,token_ends,"
                "sentence_starts,sentence_ends,token_time_starts,token_time_ends,"
                "document_embedding,image_embedding,sentence_embeddings\n"
                "doc1.txt,Doc 1,text,1,LaclauGPT,,[],[],[],AI changes institutions.,,,[],[],"
                "[],[],,,,,[]\n"
            ),
            "codes.csv": "code_name,description,color,parent_code_name\nAI,Artificial intelligence,,\n",
        }
    )
    project = import_project(payload)
    tables = export_dats_csv_tables(project)

    assert "filename,name,doctype,status" in tables["document_export_data.csv"]
    assert "code_name,description,color,parent_code_name" in tables["all_codes.csv"]
    assert "producer_type" not in tables["all_span_annotations.csv"]
    assert "whiteboard_relations" not in "\n".join(tables.values())
