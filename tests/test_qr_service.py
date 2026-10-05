from app.services.qr_service import QrService


def test_qr_generation():
    credential_number = 88990011

    # 1. Test bytes generation
    qr_bytes = QrService.generate_qr_bytes(credential_number)
    assert isinstance(qr_bytes, bytes)
    assert len(qr_bytes) > 0
    # PNG signature check: \x89PNG\r\n\x1a\n
    assert qr_bytes.startswith(b"\x89PNG")

    # 2. Test Base64 Data URI generation
    data_uri = QrService.generate_qr_data_uri(credential_number)
    assert data_uri.startswith("data:image/png;base64,")
    assert len(data_uri) > 50
