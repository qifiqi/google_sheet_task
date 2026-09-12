const utils = {};
utils.laypage = {
  limits: [100, 300, 500, 1000],
  layout: ["prev", "page", "next", "limit", "count"],
  size: 100,
  height: 800,
};
/**
 *字符串数字化
 */
utils.Number = function (val, defaultVal = -1) {
  if (val == null || val == "" || typeof val == "undefined") {
    val = defaultVal;
  }
  var newVal = Number(val);
  if (newVal == NaN) {
    return defaultVal;
  }
  return newVal;
};
/**
 *金额到亿
 */
utils.PriceToYi = function (val) {
  if (val == null || val == "" || typeof val == "undefined") {
    val = "";
  }
  var newVal = Number(val);
  if (newVal == NaN) {
    return "";
  }
  if (newVal < 100000000) {
    return Number((newVal / 10000).toFixed(2)).toLocaleString("en-US") + "万";
  }
  return Number((newVal / 100000000).toFixed(2)).toLocaleString("en-US") + "亿";
};
utils.getQueryParam = (name) => {
  try {
    let value = "";
    let query = window.location.search
      .substring(
        window.location.search.indexOf("?") + 1,
        window.location.search.length,
      )
      .split("&");
    query.forEach((item) => {
      if (item.indexOf(name + "=") > -1) {
        value = decodeURIComponent(item.replace(name + "=", ""));
        if (!value) {
          value = "";
        }
      }
    });
    return value;
  } catch (error) {
    return "";
  }
};
utils.timeFormats = (date, format) => {
  if (!date) {
    return "";
  }
  if (!format) {
    format = "YYYY-MM-DD HH:mm:ss";
  }
  return dayjs(date).format(format);
};

/**
 *金额除10000格式化
 */
utils.priceCentileFormat = function (amount) {
  var newAmount = parseFloat((amount / 10000).toFixed(4));
  if (newAmount == parseInt(newAmount)) {
    return parseInt(newAmount);
  }
  return newAmount;
};

utils.toPriceEnUs = function (amount) {
  if (amount == null || typeof amount == "undefined" || amount == "") {
    return "";
  }
  return amount.toLocaleString("en-US");
};

utils.stateBgClass = function (val) {
  switch (val) {
    case -1:
      return `style="padding:7px" class=" layui-bg-red"`;
    case 0:
      return `style="padding:7px" class=" layui-bg-orange"`;
    case 1:
      return `style="padding:7px" class=" layui-bg-blue"`;
    case 2:
      return `style="padding:7px" class=" layui-bg-green"`;
    case 3:
      return `style="padding:7px" class=" layui-bg-purple"`;
    case 9:
      return `style="padding:7px" class=" layui-bg-green"`;
    default:
      return `style="padding:7px" class=" layui-bg-blue"`;
  }
};

utils.downLoadFile = function (blo, fileName, type) {
  const blob = new Blob([blo], {
    type: type, // 添加 BOM 解决 Excel 中文乱码
  });
  const url = window.URL.createObjectURL(blob);
  window.open(url);
  // 创建隐藏的 <a> 标签触发下载
  // const a = document.createElement('a');
  // a.href = url;
  // a.download = fileName;
  // a.click();
  // 清理资源
  // window.URL.revokeObjectURL(url);
  // document.body.removeChild(a);
};

utils.layuiExportToExcel = function (cols, data, fileName) {
  var ws_data = [];
  var header = [];
  cols.forEach((item) => {
    if (item.toExcel != false) {
      header.push(item.title);
    }
  });
  ws_data.push(header);
  data.forEach((item) => {
    let info = [];
    cols.forEach((col) => {
      if (col.toExcel != false) {
        if (col.excelFormat != undefined) {
          info.push(col.excelFormat(item));
        } else {
          info.push(item[col.field]);
        }
      }
    });
    ws_data.push(info);
  });
  excelExport.export(
    ws_data,
    fileName + utils.timeFormats(new Date(), "YYYYMMDDHHmmss") + ".xlsx",
  );
};
