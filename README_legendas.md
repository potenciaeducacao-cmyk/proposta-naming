# 🎬 baixar_legendas.py — Baixador de legendas do YouTube

Script de linha de comando (CLI) em Python para baixar legendas/transcrições de
qualquer vídeo do YouTube. É **flexível**: tenta primeiro a transcrição direta
(rápida, sem baixar mídia) e, se necessário, cai automaticamente para o `yt-dlp`.

## Instalação

```bash
pip install -r requirements-legendas.txt
```

> O `yt-dlp` é usado como fallback. Para alguns vídeos/formatos ele pode exigir
> o `ffmpeg` instalado no sistema.

## Uso

```bash
# Mais simples — gera ./legendas/VIDEO_ID.pt.txt (ou en, conforme disponível)
python baixar_legendas.py "https://youtu.be/VIDEO_ID"

# Vários vídeos de uma vez
python baixar_legendas.py URL1 URL2 URL3

# Escolher idiomas (em ordem de preferência) e formato
python baixar_legendas.py URL --langs pt,en,es --format srt

# Salvar em outra pasta
python baixar_legendas.py URL -o ./minhas-legendas -f vtt

# Apenas listar os idiomas de legenda disponíveis (sem baixar)
python baixar_legendas.py URL --list
```

### Opções

| Opção            | Padrão     | Descrição                                            |
|------------------|------------|------------------------------------------------------|
| `urls`           | —          | Uma ou mais URLs (ou IDs de 11 caracteres).          |
| `--langs`        | `pt,en`    | Idiomas preferidos, em ordem.                        |
| `--format`, `-f` | `txt`      | Formato de saída: `txt`, `srt`, `vtt` ou `json`.     |
| `--output-dir`, `-o` | `legendas` | Pasta de destino.                                |
| `--list`         | —          | Lista os idiomas disponíveis e sai.                  |

## Formatos de saída

- **txt** — só o texto, linha a linha (ideal para resumir/alimentar IA).
- **srt** / **vtt** — legenda com marcação de tempo (para players de vídeo).
- **json** — segmentos com `text`, `start` e `duration` (para processamento).

## URLs aceitas

`watch?v=`, `youtu.be/`, `/shorts/`, `/embed/`, `/live/` ou o ID puro.

## Limitações

- Vídeos sem legenda (nem automática), privados, restritos por idade/região
  podem não funcionar.
- Respeite os Termos de Serviço do YouTube — use para fins pessoais/legítimos.
