from atlasleads.enrichment import _extract_emails, _extract_phones


def test_extract_emails_finds_all_unique_addresses():
    text = "Fale conosco: contato@empresa.com.br ou vendas@empresa.com.br. contato@empresa.com.br"
    assert _extract_emails(text) == {"contato@empresa.com.br", "vendas@empresa.com.br"}


def test_extract_emails_ignores_text_without_at_sign():
    assert _extract_emails("nenhum email aqui") == set()


def test_extract_phones_matches_brazilian_mobile_format():
    text = "Ligue para (11) 91234-5678 ou (11) 91234-5678 para mais informações."
    phones = _extract_phones(text)
    assert len(phones) == 1


def test_extract_phones_ignores_text_without_digits():
    assert _extract_phones("sem telefone por aqui") == set()
