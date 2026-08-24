def test_xpl_v2_page_exposes_all_data_sources(app_factory):
    response = app_factory.test_client().get('/xpl/v2')

    assert response.status_code == 200
    assert 'V2：回测数据分析' in response.get_data(as_text=True)
    assert 'Google Sheet' in response.get_data(as_text=True)
    assert '粘贴数据' in response.get_data(as_text=True)
    assert '导入 Excel' in response.get_data(as_text=True)
    assert 'id="btn-analyze-v2"' in response.get_data(as_text=True)
    assert 'date / index_return / start_return' in response.get_data(as_text=True)
    assert 'xlsx-js-style' in response.get_data(as_text=True)
    assert 'function applyV2ExportStyles' in response.get_data(as_text=True)
    assert 'XLSX.writeFile(workbook, defaultFilename' in response.get_data(as_text=True)
