const eastMoneyKlineApi = {};

eastMoneyKlineApi.SearchSecurities = function (keyword) {
  return $.ajax({
    url: "https://search-api-web.eastmoney.com/search/jsonp",
    type: "GET",
    dataType: "jsonp",
    jsonp: "cb",
    timeout: 15000,
    data: {
      param: JSON.stringify({
        uid: "",
        keyword: keyword,
        type: ["codetable"],
        client: "web",
        clientVersion: "curr",
        clientType: "web",
        param: {
          codetable: {
            pageSize: 20,
            pageIndex: 1,
            postTag: "",
            preTag: "",
          },
        },
      }),
      _: new Date().getTime(),
    },
  });
};

eastMoneyKlineApi.GetKlines = function (query) {
  return $.ajax({
    url: "https://push2his.eastmoney.com/api/qt/stock/kline/get",
    type: "GET",
    dataType: "jsonp",
    jsonp: "cb",
    timeout: 15000,
    data: {
      fields1: "f1,f2,f3,f4,f5,f6",
      fields2: "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
      ut: "b5d7eb2120497da188fdebb62aeffaf6",
      secid: query.secid,
      dect: "1",
      klt: query.klt,
      lmt: query.lmt,
      fqt: query.fqt,
      forcect: "1",
      end: "20500101",
    },
  });
};
