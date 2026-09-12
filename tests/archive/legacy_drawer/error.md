
[2026/4/2 16:06:50] 更新单元格 B7 失败，值: 0.82, 错误: [task_id=81f6fe6c-3b01-4353-9fdb-179375716a70 spreadsheet_id=1Zu8Fp35SWwdwh1BgdscdfDCjEUQbZZq2j6ssfuh3Hjc sheet_name=data1y] 更新单元格 B7 失败，值: 0.82, 错误: APIError: [400]: Invalid value at 'data.values' (type.googleapis.com/google.protobuf.ListValue), "B7"
[2026/4/2 16:06:50] 执行参数组合时出错: Traceback (most recent call last):
  File "C:\Users\Administrator\Desktop\code\google_sheet_task2\app\services\google_sheet_client.py", line 335, in update_cell
    self._retry_network_operation(_update_operation, f"update_cell({cell_address})")
  File "C:\Users\Administrator\Desktop\code\google_sheet_task2\app\services\google_sheet_client.py", line 617, in _retry_network_operation
    return operation()
           ^^^^^^^^^^^
  File "C:\Users\Administrator\Desktop\code\google_sheet_task2\app\services\google_sheet_client.py", line 333, in _update_operation
    self.worksheet.update(cell_address, cell_value)
  File "C:\Users\Administrator\Desktop\code\google_sheet_task2\.venv\Lib\site-packages\gspread\worksheet.py", line 1246, in update
    response = self.client.values_update(
               ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Administrator\Desktop\code\google_sheet_task2\.venv\Lib\site-packages\gspread\http_client.py", line 173, in values_update
    r = self.request("put", url, params=params, json=body)
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Administrator\Desktop\code\google_sheet_task2\.venv\Lib\site-packages\gspread\http_client.py", line 128, in request
    raise APIError(response)
gspread.exceptions.APIError: APIError: [400]: Invalid value at 'data.values' (type.googleapis.com/google.protobuf.ListValue), "B7"

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "C:\Users\Administrator\Desktop\code\google_sheet_task2\app\services\google_sheet_service.py", line 664, in _execute_parameter_combination
    _update_cell(attempt)
  File "C:\Users\Administrator\Desktop\code\google_sheet_task2\app\services\google_sheet_service.py", line 573, in _update_cell
    raise e
  File "C:\Users\Administrator\Desktop\code\google_sheet_task2\app\services\google_sheet_service.py", line 570, in _update_cell
    self.google_sheet.update_cell(random_key, random_value)
  File "C:\Users\Administrator\Desktop\code\google_sheet_task2\app\services\google_sheet_client.py", line 340, in update_cell
    raise Exception(error_msg) from e
Exception: [task_id=81f6fe6c-3b01-4353-9fdb-179375716a70 spreadsheet_id=1Zu8Fp35SWwdwh1BgdscdfDCjEUQbZZq2j6ssfuh3Hjc sheet_name=data1y] 更新单元格 B7 失败，值: 0.82, 错误: APIError: [400]: Invalid value at 'data.values' (type.googleapis.com/google.protobuf.ListValue), "B7"