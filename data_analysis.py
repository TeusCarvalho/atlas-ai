"""Analise deterministica de CSV/XLSX em memoria. Nao executa formulas ou codigo do usuario."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, BadZipFile
import math

import pandas as pd

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_ROWS = 50_000
MAX_COLUMNS = 80

class DatasetError(ValueError):
    pass


def _clean_scalar(value):
    if pd.isna(value):
        return None
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    if isinstance(value, (int, float)):
        v = float(value)
        return round(v, 6) if math.isfinite(v) else None
    return str(value)[:240]


def read_dataset(name: str, data: bytes) -> pd.DataFrame:
    suffix = Path(name).suffix.lower()
    if suffix not in {'.csv', '.xlsx'}:
        raise DatasetError('Formato invalido: utilize CSV ou XLSX (nao XLS ou XLSM).')
    if not data:
        raise DatasetError('O arquivo esta vazio.')
    if len(data) > MAX_UPLOAD_BYTES:
        raise DatasetError('Arquivo acima do limite de 8 MB.')
    try:
        if suffix == '.xlsx':
            if not data.startswith(b'PK'):
                raise DatasetError('Arquivo XLSX invalido.')
            try:
                with ZipFile(BytesIO(data)) as archive:
                    infos = archive.infolist()
                    if len(infos) > 1000 or sum(x.file_size for x in infos) > MAX_UNCOMPRESSED_BYTES:
                        raise DatasetError('Arquivo XLSX excede o limite de descompactacao.')
                    if any(x.flag_bits & 1 for x in infos):
                        raise DatasetError('Arquivo XLSX criptografado nao permitido.')
            except BadZipFile as exc:
                raise DatasetError('Arquivo XLSX corrompido.') from exc
            frame = pd.read_excel(BytesIO(data), engine='openpyxl', nrows=MAX_ROWS+1)
        else:
            try:
                decoded = data.decode('utf-8-sig')
            except UnicodeDecodeError:
                decoded = data.decode('cp1252')
            from io import StringIO
            try:
                frame = pd.read_csv(StringIO(decoded), sep=None, engine='python', nrows=MAX_ROWS+1)
            except (pd.errors.ParserError, ValueError):
                frame = pd.read_csv(StringIO(decoded), sep=';', nrows=MAX_ROWS+1)
    except DatasetError:
        raise
    except (ValueError, KeyError, TypeError, ImportError, OSError, pd.errors.ParserError) as exc:
        raise DatasetError(f'Nao foi possivel interpretar o arquivo: {type(exc).__name__}.') from exc
    if frame.empty:
        raise DatasetError('Nenhuma linha de dados encontrada.')
    if len(frame) > MAX_ROWS or len(frame.columns) > MAX_COLUMNS:
        raise DatasetError(f'Limite: {MAX_ROWS} linhas e {MAX_COLUMNS} colunas.')
    frame.columns = [str(c).strip()[:80] for c in frame.columns]
    if frame.columns.duplicated().any():
        raise DatasetError('Colunas repetidas apos normalizacao.')
    return frame


def analyze_dataframe(frame: pd.DataFrame, filename: str) -> dict:
    row_count = len(frame)
    cols = []
    numerics = []
    categories = []
    for column in frame.columns:
        series = frame[column]
        missing = int(series.isna().sum())
        numeric = pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series)
        info = {'nome': column, 'tipo': 'numero' if numeric else 'texto/data', 'ausentes': missing,
                'ausentes_percentual': round(missing/row_count*100,2), 'unicos': int(series.nunique(dropna=True))}
        if numeric:
            s = pd.to_numeric(series, errors='coerce').replace([float('inf'), -float('inf')], float('nan')).dropna()
            if not s.empty:
                stats = {'coluna':column, 'media':round(float(s.mean()),4), 'mediana':round(float(s.median()),4),
                         'minimo':round(float(s.min()),4), 'maximo':round(float(s.max()),4),
                         'soma':round(float(s.sum()),4)}
                numerics.append(stats)
                info['estatisticas'] = stats
        else:
            freq = series.dropna().astype(str).value_counts().head(8)
            if len(freq):
                categories.append({'coluna': column, 'valores':[{'categoria':str(k)[:80], 'quantidade':int(v)} for k,v in freq.items()]})
        cols.append(info)
    missing_cells = int(frame.isna().sum().sum())
    numeric_chart = None
    if numerics:
        col = numerics[0]['coluna']
        s = pd.to_numeric(frame[col],errors='coerce').replace([float('inf'), -float('inf')], float('nan')).dropna()
        if not s.empty:
            edges = pd.cut(s,bins=min(8,max(1,s.nunique())),duplicates='drop').value_counts().sort_index()
            numeric_chart = {'coluna':col,'faixas':[{'faixa':str(interval),'quantidade':int(count)} for interval,count in edges.items()]}
    return {'arquivo':Path(filename).name[:120], 'linhas':row_count, 'colunas_total':len(cols),
            'celulas_ausentes':missing_cells, 'linhas_duplicadas':int(frame.duplicated().sum()),
            'colunas':cols, 'numericas':numerics[:25], 'categoricas':categories[:12],
            'distribuicao':numeric_chart,
            'amostra':[{k:_clean_scalar(v) for k,v in record.items()} for record in frame.head(8).to_dict(orient='records')],
            'observacao':'Analise descritiva automatica; valores ausentes e tipos devem ser interpretados no contexto.'}
