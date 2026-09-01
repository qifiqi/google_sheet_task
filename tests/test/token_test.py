


from app.services.google_sheet_client import GoogleSheet



# https://docs.google.com/spreadsheets/d/1Sp5pVox-hlo8Uz9Y3gqO154h07YeTkXQb0u0PtXQhDA/edit?gid=1967249531#gid=1967249531
gs = GoogleSheet(spreadsheet_id="1lEguRkah4R3O8hHGzSQCcMMjk2s5MI1u3zI--VPpETQ",sheet_name='data7y', token_file=r"D:\Users\Administrator\Desktop\谷歌参数批量校验\test\token_d.json")



a = gs.get_row(1)

print(a)