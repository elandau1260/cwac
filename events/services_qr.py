"""Small, side-effect-free QR renderer used by the event flyer."""

from io import BytesIO

import qrcode


def qr_jpeg(value):
    """Encode ``value`` in a high-contrast JPEG QR image and return its bytes."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(value)
    qr.make(fit=True)

    # QR images are naturally 1-bit; convert to RGB because JPEG has no 1-bit
    # mode and a white background avoids transparency surprises in flyer apps.
    image = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    output = BytesIO()
    image.save(output, format="JPEG", quality=95, optimize=True)
    return output.getvalue()
