from io import BytesIO
from unittest.mock import patch
import pandas as pd
from fastapi.testclient import TestClient
from data_analysis import read_dataset, analyze_dataframe, DatasetError, MAX_UPLOAD_BYTES
import backend.api as api

client=TestClient(api.app)

def sid():
    return client.post('/api/session').json()['session_id']

def upload(session_id, name, data):
    return client.post('/api/data/upload',data={'session_id':session_id},files={'file':(name,data,'application/octet-stream')})

def test_valid_csv():
    s=sid()
    response=upload(s,'dados.csv',b'grupo;valor\nA;12\nB;18\nA;30\n')
    assert response.status_code==200,response.text
    res=response.json()['resumo']
    assert res['linhas']==3 and res['colunas_total']==2
    assert res['numericas'][0]['soma']==60
    assert len(res['amostra'])==3

def test_excel():
    stream=BytesIO()
    pd.DataFrame({'x':[1,2],'y':['a','b']}).to_excel(stream,index=False)
    response=upload(sid(),'dados.xlsx',stream.getvalue())
    assert response.status_code==200,response.text
    assert response.json()['resumo']['linhas']==2

def test_reject_extension_and_oversize():
    s=sid()
    assert upload(s,'evil.xlsm',b'junk').status_code==422
    assert upload(s,'evil.csv',b'a\n'+b'x'*(MAX_UPLOAD_BYTES+1)).status_code==422

def test_reject_invalid_xlsx():
    assert upload(sid(),'not.xlsx',b'not excel').status_code==422

def test_summary_and_clear():
    s=sid()
    assert client.post('/api/data/summary',json={'session_id':s}).status_code==404
    assert upload(s,'data.csv',b'value\n42\n').status_code==200
    assert client.post('/api/data/summary',json={'session_id':s}).status_code==200
    assert client.post('/api/session/clear',json={'session_id':s}).status_code==200
    assert client.post('/api/data/summary',json={'session_id':s}).status_code==404

def test_missing_duplicate_and_numeric():
    df=pd.DataFrame({'valor':[2,2,None], 'grupo':['A','A','B']})
    result=analyze_dataframe(df,'teste.csv')
    assert result['celulas_ausentes']==1
    assert result['linhas_duplicadas']==1
    assert result['numericas'][0]['media']==2

def test_no_filename_and_unknown_session():
    assert upload('f'*32,'ok.csv',b'a\n1\n').status_code==404
    assert upload(sid(),'x.py',b'x').status_code==422
