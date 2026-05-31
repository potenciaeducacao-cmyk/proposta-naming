#!/usr/bin/env python3
"""Baixa legendas/transcrições de vídeos do YouTube via terminal.

Estratégia (flexível, com fallback automático):
  1. Tenta a `youtube-transcript-api` — rápida, sem baixar mídia, ótima para texto.
  2. Se não houver legenda por essa via (ou para formatos como vtt), usa o `yt-dlp`.

Formatos de saída suportados: txt, srt, vtt, json.

Exemplos:
  python baixar_legendas.py "https://youtu.be/VIDEO_ID"
  python baixar_legendas.py URL1 URL2 --langs pt,en --format srt
  python baixar_legendas.py URL --list           # lista idiomas disponíveis
  python baixar_legendas.py URL --format vtt -o ./legendas
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

# Cobre as formas mais comuns de URL do YouTube (watch, youtu.be, shorts, embed)
# e também aceita um ID "cru" de 11 caracteres.
_ID_RE = re.compile(
    r"(?:v=|/shorts/|/embed/|youtu\.be/|/v/|/live/)([0-9A-Za-z_-]{11})"
)


def extrair_video_id(url: str) -> str | None:
    """Extrai o ID de 11 caracteres de uma URL (ou retorna o próprio ID)."""
    url = url.strip()
    if re.fullmatch(r"[0-9A-Za-z_-]{11}", url):
        return url
    m = _ID_RE.search(url)
    return m.group(1) if m else None


def _format_timestamp(seconds: float, *, vtt: bool = False) -> str:
    """Converte segundos para HH:MM:SS,mmm (SRT) ou HH:MM:SS.mmm (VTT)."""
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    sep = "." if vtt else ","
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _segmentos_para_srt(segmentos: list[dict]) -> str:
    linhas = []
    for i, seg in enumerate(segmentos, start=1):
        inicio = seg["start"]
        fim = inicio + seg.get("duration", 0)
        linhas.append(str(i))
        linhas.append(
            f"{_format_timestamp(inicio)} --> {_format_timestamp(fim)}"
        )
        linhas.append(seg["text"])
        linhas.append("")
    return "\n".join(linhas)


def _segmentos_para_vtt(segmentos: list[dict]) -> str:
    linhas = ["WEBVTT", ""]
    for seg in segmentos:
        inicio = seg["start"]
        fim = inicio + seg.get("duration", 0)
        linhas.append(
            f"{_format_timestamp(inicio, vtt=True)} --> "
            f"{_format_timestamp(fim, vtt=True)}"
        )
        linhas.append(seg["text"])
        linhas.append("")
    return "\n".join(linhas)


def _segmentos_para_txt(segmentos: list[dict]) -> str:
    return "\n".join(seg["text"] for seg in segmentos)


def formatar(segmentos: list[dict], fmt: str) -> str:
    if fmt == "txt":
        return _segmentos_para_txt(segmentos)
    if fmt == "json":
        return json.dumps(segmentos, ensure_ascii=False, indent=2)
    if fmt == "srt":
        return _segmentos_para_srt(segmentos)
    if fmt == "vtt":
        return _segmentos_para_vtt(segmentos)
    raise ValueError(f"Formato não suportado: {fmt}")


# ---------------------------------------------------------------------------
# Estratégia 1: youtube-transcript-api
# ---------------------------------------------------------------------------


def _via_transcript_api(video_id: str, langs: list[str], listar: bool):
    """Retorna (segmentos, idioma) ou None se a lib/legenda não estiver disponível.

    Compatível tanto com a API nova (v1.x: instância + .fetch()/.list())
    quanto com a antiga (estática: .get_transcript()/.list_transcripts()).
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None  # lib não instalada → deixa o yt-dlp assumir

    # ---- API nova (>= 1.0) ----
    if hasattr(YouTubeTranscriptApi, "fetch"):
        api = YouTubeTranscriptApi()
        try:
            disponiveis = api.list(video_id)
        except Exception as e:  # noqa: BLE001
            print(f"  · transcript-api indisponível: {e}", file=sys.stderr)
            return None
        if listar:
            print(f"Idiomas disponíveis para {video_id}:")
            for t in disponiveis:
                tipo = "auto" if t.is_generated else "manual"
                print(f"  - {t.language_code} ({t.language}) [{tipo}]")
            return "LISTED"
        try:
            fetched = disponiveis.find_transcript(langs).fetch()
        except Exception:
            try:
                fetched = api.fetch(video_id, languages=langs)
            except Exception as e:  # noqa: BLE001
                print(f"  · transcript-api sem legenda nos idiomas {langs}: {e}",
                      file=sys.stderr)
                return None
        segmentos = [
            {"text": s.text, "start": s.start, "duration": s.duration}
            for s in fetched
        ]
        idioma = getattr(fetched, "language_code", langs[0])
        return segmentos, idioma

    # ---- API antiga ----
    try:
        if listar:
            print(f"Idiomas disponíveis para {video_id}:")
            for t in YouTubeTranscriptApi.list_transcripts(video_id):
                tipo = "auto" if t.is_generated else "manual"
                print(f"  - {t.language_code} ({t.language}) [{tipo}]")
            return "LISTED"
        segmentos = YouTubeTranscriptApi.get_transcript(video_id, languages=langs)
        return segmentos, langs[0]
    except Exception as e:  # noqa: BLE001
        print(f"  · transcript-api sem legenda: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Estratégia 2: yt-dlp (fallback)
# ---------------------------------------------------------------------------


def _via_yt_dlp(url: str, langs: list[str], fmt: str, output_dir: Path,
               listar: bool) -> bool:
    """Usa o yt-dlp como fallback. Retorna True em caso de sucesso."""
    if not shutil.which("yt-dlp"):
        print("  · yt-dlp não encontrado no PATH (pip install yt-dlp).",
              file=sys.stderr)
        return False

    if listar:
        subprocess.run(["yt-dlp", "--list-subs", "--skip-download", url],
                       check=False)
        return True

    sub_fmt = "vtt" if fmt in ("vtt", "txt", "json") else "srt"
    cmd = [
        "yt-dlp",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs", ",".join(langs),
        "--sub-format", sub_fmt,
        "--convert-subs", "srt" if fmt == "srt" else sub_fmt,
        "--skip-download",
        "--output", str(output_dir / "%(title)s.%(ext)s"),
        url,
    ]
    print("  · usando yt-dlp como fallback...", file=sys.stderr)
    resultado = subprocess.run(cmd, check=False)
    return resultado.returncode == 0


# ---------------------------------------------------------------------------
# Orquestração por vídeo
# ---------------------------------------------------------------------------


def processar(url: str, langs: list[str], fmt: str, output_dir: Path,
              listar: bool) -> bool:
    video_id = extrair_video_id(url)
    if not video_id:
        print(f"✗ Não consegui extrair o ID do vídeo de: {url}", file=sys.stderr)
        return False

    print(f"▶ Processando {video_id} ...", file=sys.stderr)

    resultado = _via_transcript_api(video_id, langs, listar)

    if resultado == "LISTED":
        return True

    if resultado:
        segmentos, idioma = resultado
        output_dir.mkdir(parents=True, exist_ok=True)
        destino = output_dir / f"{video_id}.{idioma}.{fmt}"
        destino.write_text(formatar(segmentos, fmt), encoding="utf-8")
        print(f"✓ Legenda salva: {destino}")
        return True

    # Fallback para yt-dlp (também cobre o caso --list quando a API falha).
    output_dir.mkdir(parents=True, exist_ok=True)
    if _via_yt_dlp(url, langs, fmt, output_dir, listar):
        if not listar:
            print(f"✓ Legenda(s) salva(s) em: {output_dir}")
        return True

    print(f"✗ Nenhuma legenda encontrada para {url}", file=sys.stderr)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Baixa legendas/transcrições de vídeos do YouTube.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("urls", nargs="+", help="Uma ou mais URLs (ou IDs) de vídeos.")
    parser.add_argument(
        "--langs", default="pt,en",
        help="Idiomas preferidos, em ordem (ex.: pt,en,es). Padrão: pt,en",
    )
    parser.add_argument(
        "--format", "-f", default="txt", choices=["txt", "srt", "vtt", "json"],
        help="Formato de saída. Padrão: txt",
    )
    parser.add_argument(
        "--output-dir", "-o", default="legendas",
        help="Pasta de destino. Padrão: ./legendas",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="Apenas lista os idiomas de legenda disponíveis (não baixa).",
    )
    args = parser.parse_args(argv)

    langs = [x.strip() for x in args.langs.split(",") if x.strip()]
    output_dir = Path(args.output_dir)

    sucessos = 0
    for url in args.urls:
        if processar(url, langs, args.format, output_dir, args.list):
            sucessos += 1

    total = len(args.urls)
    if not args.list:
        print(f"\nConcluído: {sucessos}/{total} vídeo(s) com sucesso.",
              file=sys.stderr)
    return 0 if sucessos == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
