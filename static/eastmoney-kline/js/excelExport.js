const excelExport = {};

/**
 * 导出二维数据到 Excel。
 *
 * rows 的第一行必须是标题，后续每一行是业务数据。组件只负责工作簿和样式，
 * 页面保留自身的数据查询、字段格式化和数据排序，避免在公共组件中混入业务逻辑。
 */
excelExport.export = function (rows, fileName, options) {
  if (typeof XLSX === "undefined") {
    throw new Error("SheetJS 加载失败");
  }
  if (!Array.isArray(rows) || rows.length === 0) {
    throw new Error("没有可导出的数据");
  }

  options = options || {};
  var worksheet = XLSX.utils.aoa_to_sheet(rows);
  applyCellStyles(worksheet, rows, options.getCellStyle);
  worksheet["!cols"] = getColumnWidths(rows[0], options.columnWidths);

  var workbook = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(workbook, worksheet, options.sheetName || "Sheet1");
  XLSX.writeFile(workbook, ensureFileExtension(fileName));
};

/**
 * 导出多个工作表。每个 sheet 使用与 export 相同的 rows、sheetName、
 * columnWidths 和 getCellStyle 配置，适用于数据与说明需要分开的场景。
 */
excelExport.exportSheets = function (sheets, fileName) {
  if (typeof XLSX === "undefined") {
    throw new Error("SheetJS 加载失败");
  }
  if (!Array.isArray(sheets) || sheets.length === 0) {
    throw new Error("没有可导出的工作表");
  }

  var workbook = XLSX.utils.book_new();
  sheets.forEach(function (sheet, index) {
    if (!sheet || !Array.isArray(sheet.rows) || sheet.rows.length === 0) {
      throw new Error("工作表数据不能为空");
    }
    var worksheet = XLSX.utils.aoa_to_sheet(sheet.rows);
    applyCellStyles(worksheet, sheet.rows, sheet.getCellStyle);
    worksheet["!cols"] = getColumnWidths(sheet.rows[0], sheet.columnWidths);
    XLSX.utils.book_append_sheet(workbook, worksheet, sheet.sheetName || "Sheet" + (index + 1));
  });
  XLSX.writeFile(workbook, ensureFileExtension(fileName));
};

/**
 * 将对象数组按列定义导出。普通列表页应优先使用此方法，页面仅声明列标题、
 * 字段和必要的格式化规则，避免重复创建 ws_data、标题行和数据行。
 *
 * @param {Array} data 要导出的对象数组。
 * @param {Array} columns 列定义：title 为标题；field 为对象字段；
 *                        formatter(item, rowIndex) 可用于金额、日期等业务格式化。
 * @param {String} fileName 导出的文件名，可省略 .xlsx 后缀。
 * @param {Object} options 与 export 方法相同的工作表和样式配置。
 */
excelExport.exportByColumns = function (data, columns, fileName, options) {
  if (!Array.isArray(data)) {
    throw new Error("导出数据格式错误");
  }
  if (!Array.isArray(columns) || columns.length === 0) {
    throw new Error("导出列不能为空");
  }

  var rows = [
    columns.map(function (column) {
      return column.title;
    }),
  ];
  data.forEach(function (item, rowIndex) {
    rows.push(
      columns.map(function (column) {
        return column.formatter
          ? column.formatter(item, rowIndex)
          : item[column.field];
      }),
    );
  });
  excelExport.export(rows, fileName, options);
};

/**
 * 按项目统一规范写入单元格样式。
 * 标题行使用淡黄色加粗，所有单元格使用微软雅黑并居中对齐。
 * getCellStyle 用于覆盖特定数据格，例如触发价格需要红色字体。
 */
function applyCellStyles(worksheet, rows, getCellStyle) {
  rows.forEach(function (row, rowIndex) {
    row.forEach(function (value, columnIndex) {
      var cell = worksheet[
        XLSX.utils.encode_cell({ r: rowIndex, c: columnIndex })
      ];
      if (!cell) {
        return;
      }
      var style = getDefaultCellStyle(rowIndex === 0);
      if (getCellStyle) {
        mergeCellStyle(
          style,
          getCellStyle(rowIndex, columnIndex, value, rowIndex === 0),
        );
      }
      cell.s = style;
    });
  });
}

/**
 * 返回新样式对象，避免同一个样式对象被后续单元格修改。
 */
function getDefaultCellStyle(isHeader) {
  var style = {
    font: {
      name: "Microsoft YaHei",
      bold: isHeader,
    },
    alignment: {
      horizontal: "center",
      vertical: "center",
    },
  };
  if (isHeader) {
    style.fill = {
      patternType: "solid",
      fgColor: { rgb: "FFF2CC" },
    };
  }
  return style;
}

/**
 * 合并页面传入的样式覆盖项，只处理 Excel 样式实际使用的三层字段。
 */
function mergeCellStyle(style, customStyle) {
  if (!customStyle) {
    return;
  }
  ["font", "fill", "alignment"].forEach(function (key) {
    if (customStyle[key]) {
      style[key] = Object.assign(style[key] || {}, customStyle[key]);
    }
  });
}

/**
 * 未指定列宽时使用 15 个字符宽度，页面可传入 columnWidths 覆盖。
 */
function getColumnWidths(headers, columnWidths) {
  return headers.map(function (header, index) {
    return { wch: columnWidths && columnWidths[index] ? columnWidths[index] : 15 };
  });
}

function ensureFileExtension(fileName) {
  return /\.xlsx$/i.test(fileName) ? fileName : fileName + ".xlsx";
}
