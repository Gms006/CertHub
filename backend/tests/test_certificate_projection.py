from app.services.certificate_projection import parse_subject_summary


def test_parse_subject_summary_detects_cpf_in_cn_with_many_dn_digits():
    subject = (
        "CN=EMPRESA EXEMPLO 12345678901,"
        "2.5.4.15=Private Organization,"
        "2.5.4.5=12345678000199"
    )

    summary = parse_subject_summary(subject, "CN=Autoridade Certificadora")

    assert summary["document_type"] == "CPF"
    assert summary["document_unmasked"] == "12345678901"
    assert summary["document_masked"] == "CPF ***.***.***-01"


def test_parse_subject_summary_detects_cnpj_with_formatted_value():
    subject = "CN=EMPRESA EXEMPLO, O=EMPRESA, SERIALNUMBER=12.345.678/0001-95"

    summary = parse_subject_summary(subject, "CN=Autoridade Certificadora")

    assert summary["document_type"] == "CNPJ"
    assert summary["document_unmasked"] == "12345678000195"
    assert summary["document_masked"] == "CNPJ 12********0195"
