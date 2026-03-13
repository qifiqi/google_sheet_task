import pandas as pd
import numpy as np

print(f"{0.010637823522264611:.2}")
print("2023-01-30 00:00:00/2023-12-29 00:00:00".split('/'))
# # # 1. 加载四个表格
# df1 = pd.DataFrame('', index=range(19), columns=range(4))
# df1.iloc[3] = ['指标类型',"指标","指数",'']
#
#
#
#
#
#
# # df2 = pd.DataFrame('2', index=range(5), columns=range(8))
# # df3 = pd.DataFrame('3', index=range(5), columns=range(8))
# # df4 = pd.DataFrame('4', index=range(84), columns=range(3))
#
# # # 2. 创建空的目标DataFrame（根据你的布局需求调整大小）
# # # 假设需要10行10列的布局
# target_df = pd.DataFrame(np.nan, index=range(100), columns=range(100))
#
# # # 3. 将每个表格放到指定位置
# # # 示例：将df1放在A1:C4区域，df2放在E1:G6区域等
# target_df.iloc[0:df1.shape[0], 0:df1.shape[1]] = df1.values
# # target_df.iloc[21:21+df2.shape[0], 0:df2.shape[1]] = df2.values
# # target_df.iloc[27:27+df3.shape[0], 0:df3.shape[1]] = df3.values
# # target_df.iloc[3:3+df4.shape[0], 10:10+df4.shape[1]] = df4.values
# # # 继续添加其他表格...
#
# # # 4. 保存为CSV
# target_df.to_csv('combined_output.csv', index=False, header=False)
#
#
#

#
#
#
#
# import pandas as pd
# import numpy as np
# from openpyxl import Workbook
# from openpyxl.styles import Alignment, PatternFill, Border, Side, Font
# from openpyxl.utils import get_column_letter
#
# # 1. 创建示例数据（使用你提供的数据结构）
# df1 = pd.DataFrame('数据1', index=range(19), columns=range(4))
# df2 = pd.DataFrame('数据2', index=range(5), columns=range(8))
# df3 = pd.DataFrame('数据3', index=range(5), columns=range(8))
# df4 = pd.DataFrame('数据4', index=range(84), columns=range(3))
#
# # 2. 创建Excel工作簿
# wb = Workbook()
# ws = wb.active
# ws.title = "合并表格"
#
# # 3. 将每个表格放到指定位置
# # 表格1：放在A1:D19区域
# for i in range(len(df1)):
#     for j in range(len(df1.columns)):
#         ws.cell(row=i+1, column=j+1, value=df1.iat[i, j])
#
# # 表格2：放在A22:H26区域
# start_row_2 = 22
# for i in range(len(df2)):
#     for j in range(len(df2.columns)):
#         ws.cell(row=start_row_2+i, column=j+1, value=df2.iat[i, j])
#
# # 表格3：放在A28:H32区域
# start_row_3 = 28
# for i in range(len(df3)):
#     for j in range(len(df3.columns)):
#         ws.cell(row=start_row_3+i, column=j+1, value=df3.iat[i, j])
#
# # 表格4：放在K4:M87区域（第4行开始，第11列开始）
# start_row_4 = 4
# start_col_4 = 11  # K列
# for i in range(len(df4)):
#     for j in range(len(df4.columns)):
#         ws.cell(row=start_row_4+i, column=start_col_4+j, value=df4.iat[i, j])
#
# # 4. 添加合并单元格（示例）
# # 示例1：合并A20:C20作为表格1的备注
# ws.merge_cells('B1:D1')
# ws['B1'] = "QQQ"
# ws['B1'].alignment = Alignment(horizontal='center', vertical='center')
#
# # 示例2：合并A21:H21作为分隔行
# ws.merge_cells('B2:D2')
# ws['B2'] = "2019/1/1-2025/12/31"
# ws['B2'].alignment = Alignment(horizontal='center')
# ws['B2'].fill = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
#
# # 示例3：合并A27:H27作为表格3的标题
# ws.merge_cells('A21:H21')
# ws['A21'] = "表格2标题"
# ws['A21'].alignment = Alignment(horizontal='center', vertical='center')
# ws['A21'].font = Font(bold=True, size=12)
#
# # 示例4：合并A27:H27作为表格3的标题
# ws.merge_cells('A27:H27')
# ws['A27'] = "表格3标题"
# ws['A27'].alignment = Alignment(horizontal='center', vertical='center')
# ws['A27'].font = Font(bold=True, size=12)
#
# # 5. 设置列宽
# column_widths = {
#     'A': 12, 'B': 12, 'C': 12, 'D': 12,
#     'E': 12, 'F': 12, 'G': 12, 'H': 12,
#     'K': 15, 'L': 15, 'M': 15
# }
#
# for col_letter, width in column_widths.items():
#     ws.column_dimensions[col_letter].width = width
#
# # 6. 添加边框样式
# thin_border = Border(
#     left=Side(style='thin'),
#     right=Side(style='thin'),
#     top=Side(style='thin'),
#     bottom=Side(style='thin')
# )
#
# # 为表格区域添加边框
# # 表格1区域
# for row in range(1, 20):
#     for col in range(1, 5):
#         ws.cell(row=row, column=col).border = thin_border
#
# # 表格2区域
# for row in range(22, 27):
#     for col in range(1, 9):
#         ws.cell(row=row, column=col).border = thin_border
#
# # 表格3区域
# for row in range(28, 33):
#     for col in range(1, 9):
#         ws.cell(row=row, column=col).border = thin_border
#
# # 表格4区域
# for row in range(4, 88):
#     for col in range(11, 14):
#         ws.cell(row=row, column=col).border = thin_border
#
# # 7. 设置对齐方式
# for row in ws.iter_rows(min_row=1, max_row=100, min_col=1, max_col=13):
#     for cell in row:
#         if cell.value:
#             cell.alignment = Alignment(horizontal='center', vertical='center')
#
# # 8. 保存文件
# output_path = "合并表格.xlsx"
# wb.save(output_path)
# print(f"Excel文件已保存到：{output_path}")
