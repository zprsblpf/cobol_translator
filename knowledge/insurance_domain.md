# 保险领域术语对照（COBOL → Java）

## 核心业务字段

| COBOL 变量名 | 含义 | Java 字段名建议 |
|------------|------|--------------|
| CHDRNO | 保单号 | policyNo / chdrno |
| CHDRCOY | 保单公司代码 | policyCompany |
| CLNTNO | 客户号 | clientNo |
| AGNTNO | 代理人号 | agentNo |
| PTDATE | 保单生效日期 | policyEffectDate |
| LOAN-DATE | 贷款日期 | loanDate |
| TMLCLST | 模板/信函列表 | templateList |
| TMLCPKY | 模板关键字 | templateKey |
| COVR | 险种承保 | coverage |
| COVA | 险种附加 | coverageAddon |
| RSKNO | 风险编号 | riskNo |
| LIFE | 被保险人 | insured |
| BENEFICIARY | 受益人 | beneficiary |
| WSAA-PVALUE | 保单价值 | policyValue |
| WSAA-CSV | 现金价值 | cashSurrenderValue |
| WSAA-RPU | 缴清保额 | reducedPaidUp |

## IO 子程序业务含义

| COBOL CALL | 业务含义 |
|-----------|---------|
| TMLCLSTIO | 信函模板列表（Letter Template List） |
| TMLCPKYIO | 信函模板关键字（Template Key） |
| CHDRENQIO | 保单查询（Policy Enquiry） |
| ITEMIO | 通用配置项（Item/Parameter Table） |
| DESCIO | 描述表（Description Table） |
| COVRMJAIO | 险种多语言（Coverage Multi-language） |
| COVRIO | 险种表（Coverage Table） |
| EUFKPKYIO | 欧洲外键（EU Foreign Key） |
| DATCON1 | 日期格式转换1（Date Conversion 1） |
| DATCON3 | 日期频率转换（Date Conversion with Frequency） |
| DATCON6 | 日期计算6（Date Calculation 6） |

## LETCMNT-PARAMS（入参结构）

```cobol
01 LETCMNT-PARAMS.
   03 LETCMNT-COMPANY    PIC X(01)
   03 LETCMNT-REQUEST-COMPANY  PIC X(01)
   03 LETCMNT-CHDRNO     PIC X(08)
   03 LETCMNT-LANGUAGE   PIC X(02)
   03 LETCMNT-CLNTNO     PIC X(08)
```
```java
public class LetcmntParams {
    private String company;
    private String requestCompany;
    private String chdrno;       // 保单号
    private String language;     // 语言代码
    private String clntno;       // 客户号
}
```

## 常用业务逻辑模式

### 保单查询
```java
// COBOL: 查询保单基本信息
ChdrenqKey key = new ChdrenqKey(chdrno, company);
ChdrenqRecord policy = chdrenqRepository.findByKey(key);
if (policy == null) {
    throw new PolicyNotFoundException(chdrno);
}
```

### 信函模板处理
```java
// 按公司+语言查询信函模板
TmlclstKey key = new TmlclstKey(company, language);
List<TmlclstRecord> templates = tmlclstRepository.findByCompanyAndLanguage(company, language);
```

### ITEM 通用配置
```java
// ITEM 表是保险系统中最常用的通用配置表
// ITEMPFX=前缀, ITEMTYPE=类型, ITEMSEQ=序号
ItemKey key = new ItemKey(itemPfx, itemType, itemSeq);
ItemRecord config = itemRepository.findByKey(key);
```
