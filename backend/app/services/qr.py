"""QR code generation as inline SVG (no raster image backend required)."""
from __future__ import annotations

import qrcode


def qr_svg(data: str, *, box: int = 8, border: int = 4, dark: str = "#0f172a") -> str:
    """Render `data` as a crisp, scalable SVG QR code built from the module matrix."""
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=box, border=border)
    qr.add_data(data)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    n = len(matrix)
    dim = (n + border * 2) * box
    rects = []
    for r, row in enumerate(matrix):
        for c, cell in enumerate(row):
            if cell:
                x = (c + border) * box
                y = (r + border) * box
                rects.append(f'<rect x="{x}" y="{y}" width="{box}" height="{box}"/>')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{dim}" height="{dim}" '
        f'viewBox="0 0 {dim} {dim}" shape-rendering="crispEdges">'
        f'<rect width="{dim}" height="{dim}" fill="#ffffff"/>'
        f'<g fill="{dark}">{"".join(rects)}</g></svg>'
    )
