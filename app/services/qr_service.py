import base64
from io import BytesIO
import qrcode
from qrcode.constants import ERROR_CORRECT_M


class QrService:
    """Generates QR codes for door reader presentations."""

    @staticmethod
    def generate_qr_bytes(credential_number: int) -> bytes:
        """Renders credential number as a PNG image in bytes."""
        qr = qrcode.QRCode(
            version=1,
            error_correction=ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(str(credential_number))
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()

    @classmethod
    def generate_qr_data_uri(cls, credential_number: int) -> str:
        """Returns base64 data URI string suitable for direct HTML/mobile rendering."""
        img_bytes = cls.generate_qr_bytes(credential_number)
        encoded = base64.b64encode(img_bytes).decode("utf-8")
        return f"data:image/png;base64,{encoded}"
