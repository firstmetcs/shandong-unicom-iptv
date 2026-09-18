# shandong-unicom-iptv

# 山东联通华为平台IPTV认证与频道列表获取


本项目用于在iStoreOS中实现从认证到获取频道信息的完整流程

> - 本文认证主流程参考自时光轨车的[SDU-IPTV-Mock](https://github.com/sggc/SDU-IPTV-Mock)
> - 整理频道、抓取频道节目单以及Authenticator暴力破解脚本参考自昆山论坛[群晖安装rtp2httpd与get_iptv_channels。实现自动抓包山东联通iptv自动生成m3u。](https://www.right.com.cn/forum/forum.php?mod=viewthread&tid=8473399)

***

## 认证流程分析

通过抓包分析，发现IPTV认证流程分为以下几个步骤：

### 步骤1：访问AuthenticationURL

机顶盒首先向EDS服务器发起认证请求：

```
GET /EDS/jsp/AuthenticationURL?UserID=<UserID>&Action=Login&FCCSupport=1 HTTP/1.1
Host: 27.xxx.xxx.xxx:8082
User-Agent: B700-V2A|Mozilla|5.0|ztebw(Chrome)|1.2.0
```

服务器返回302重定向，并设置Cookie：

```
HTTP/1.1 302 Found
Set-Cookie: EPGIP_PORT="123.xxx.xxx.xxx:33200"; Version=1; Max-Age=86400
Location: http://123.xxx.xxx.xxx:33200/EPG/jsp/AuthenticationURL?UserID=<UserID>&Action=Login
```

**关键发现**：

- EDS服务器负责初始认证和EPG服务器分配
- 通过Cookie下发实际的EPG服务器地址

### 步骤2：获取EncryptToken

跟随重定向后，向EPG服务器提交authLogin请求：

```
POST /EPG/jsp/authLoginHWCU.jsp HTTP/1.1
Host: 123.xxx.xxx.xxx:33200

UserID=<UserID>&VIP=
```

返回HTML中包含`EncryptToken`：

```html
<script>
var EncryptToken = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx";
</script>
```

### 步骤3：生成Authenticator并验证

这是最关键的一步。前人早已经研究，其使用**3DES加密**（实际退化为DES），明文格式为：

```
{Random}${EncryptToken}${UserID}${STBID}${IP}${MAC}$Reserved$CTC
```

例如：

```
22295825$977C790C5E3FEF5798D998CBF6C70B69$05xxxxxxxxxx$DExxxxxxxxxxxxxxxxxxxxxx$10.xxx.xxx.xxx$C0:xx:xx:xx:xx:xx$$CTC
```

注意：

之前看过很多教程，大多都是电信运营商，明文末尾是CTC，我就想当然认为联通是CU，踩了坑

### 密钥破解

密钥是一个8位数字。编写穷举脚本进行暴力破解，最终找到有效密钥：**`04260600`**

总共可以穷举出256个等效密钥，值得注意的是，其中一个是IPTV的密码

### 步骤4：获取频道列表

认证成功后，使用获取到的`UserToken`和`stbid`请求频道列表：

```
POST /EPG/jsp/getchannellistHWCU.jsp HTTP/1.1
Host: 123.xxx.xxx.xxx:33200

conntype=dhcp&UserToken=xxxxxxxx&stbid=xxxxxxxx&SupportHD=1&UserID=<UserID>&Lang=1
```

返回的HTML中包含频道信息：

```html
<script>
var iRet = Authentication.CTCSetConfig('Channel','ChannelID="xxx",ChannelName="CCTV-1高清",UserChannelID="1",ChannelURL="igmp://xxx.xxx.xxx.xxx:xxxx",...');
</script>
```

***

## 完整鉴权认证流程图

```
步骤1: 初始认证请求
┌──────────┐                    ┌──────────┐
│ 机顶盒    │ ───GET──────────>  │ EDS服务器 │
│          │ /EDS/jsp/AuthenticationURL    │27.223.126.136:8082
│          │ ?UserID=xxx&Action=Login      │
└──────────┘                    └──────────┘
     │                                │
     │                                │ 302重定向
     │                                │ Location: EPG服务器
     │                                ↓
     │                         ┌──────────┐
     └─────────────────────────│ EPG服务器 │
                               │123.133.95.40:33200
                               └──────────┘

步骤2: 获取认证表单
┌──────────┐                    ┌──────────┐
│ 机顶盒    │ ───GET──────────>  │ EPG服务器 │
│          │ /EPG/jsp/AuthenticationURL    │
└──────────┘                    └──────────┘
     │                                │
     │                                │ 返回HTML表单
     │ <──────────────────────────────┘
     │    <form action="authLoginHWCU.jsp">
     │    <input name="UserID" value="xxx">
     │    <input name="VIP" value="">

步骤3: 提交登录信息
┌──────────┐                    ┌──────────┐
│ 机顶盒    │ ───POST─────────>  │ EPG服务器 │
│          │ /EPG/jsp/authLoginHWCU.jsp    │
│          │ UserID=xxx                    │
│          │ VIP=                          │
└──────────┘                    └──────────┘
     │                                │
     │                                │ 返回EncryptToken和userToken
     │ <──────────────────────────────┘
     │    EncryptToken = "xxx"
     │    userToken = "xxx"

步骤4: 提交认证信息（关键步骤）
┌──────────┐                   ┌───────────┐
│ 机顶盒    │ ───POST─────────> │ EPG服务器  │
│          │ /EPG/jsp/ValidAuthenticationHWCU.jsp
│          │ UserID=xxx                    │
│          │ Authenticator=加密字符串        │ ← 3DES加密
│          │ STBType=xxx                   │
│          │ STBID=xxx                     │
│          │ mac=xxx                       │
└──────────┘                    └──────────┘
     │                                │
     │                                │ 验证成功，返回Session
     │ <──────────────────────────────┘
     │    JSESSIONID = "xxx"
     │    UserToken = "xxx"
     │    stbid = "xxx"

步骤5: 获取频道列表
┌──────────┐                   ┌────────────┐
│ 机顶盒    │ ───POST─────────> │ EPG服务器   │
│          │ /EPG/jsp/getchannellistHWCU.jsp│
│          │ UserToken=xxx                  │
│          │ tempKey=xxx                    │
│          │ stbid=xxx                      │
│          │ Cookie: JSESSIONID=xxx         │
└──────────┘                    └───────────┘
     │                                │
     │                                │ 返回频道列表
     │ <──────────────────────────────┘
```

***

## 完整鉴权认证流程

#### 接口1: 初始认证入口

```
URL: http://{EDS服务器}:8082/EDS/jsp/AuthenticationURL
方法: GET
参数:
  - UserID: {用户业务账号}
  - Action: Login
  - FCCSupport: 1

响应: 302重定向到EPG服务器
Location: http://{EPG服务器IP}:33200/EPG/jsp/AuthenticationURL?UserID={xxx}&Action=Login&FCCSupport=1
```

#### 接口2: 获取认证表单

```
URL: http://{EPG服务器IP}:33200/EPG/jsp/AuthenticationURL
方法: GET
参数:
  - UserID: {用户业务账号}
  - Action: Login
  - FCCSupport: 1

响应: HTML页面，包含表单
<form action="authLoginHWCU.jsp" name="authform" method="post">
  <input type="hidden" name="UserID" value="{用户业务账号}">
  <input type="hidden" name="VIP" value="">
</form>
```

#### 接口3: 提交登录信息

```
URL: http://{EPG服务器IP}:33200/EPG/jsp/authLoginHWCU.jsp
方法: POST
Content-Type: application/x-www-form-urlencoded
参数:
  - UserID: {用户业务账号}
  - VIP: (空)

响应: HTML页面，包含JavaScript变量
var EncryptToken = "{加密令牌}";
var userToken = "{用户令牌}";
```

#### 接口4: 提交认证信息（核心接口）

```
URL: http://{EPG服务器IP}:33200/EPG/jsp/ValidAuthenticationHWCU.jsp
方法: POST
Content-Type: application/x-www-form-urlencoded
参数:
  - UserID: {用户业务账号}
  - Lang: 0
  - SupportHD: 1
  - NetUserID: {运营商认证账号}
  - Authenticator: {3DES加密串}
  - STBType: {机顶盒型号}
  - STBVersion: {机顶盒版本}
  - conntype: dhcp
  - STBID: {设备唯一标识}
  - templateName: (空)
  - areaId: (空)
  - userToken: (从步骤3获取)
  - userGroupId: (空)
  - productPackageId: (空)
  - mac: {MAC地址}
  - UserField: (空)
  - SoftwareVersion: (空)
  - IsSmartStb: undefined
  - desktopId: undefined
  - stbmaker: (空)
  - VIP: (空)

响应: HTML页面，包含
  - Set-Cookie: JSESSIONID={会话ID}
  - UserToken = "{用户令牌}"
  - stbid = "{设备ID}"
```

#### 接口5: 获取频道列表

```
URL: http://{EPG服务器IP}:33200/EPG/jsp/getchannellistHWCU.jsp
方法: POST
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID={会话ID}
参数:
  - conntype: dhcp
  - UserToken: {用户令牌}
  - tempKey: {临时密钥}
  - stbid: {短设备ID}
  - SupportHD: 1
  - UserID: {用户业务账号}
  - Lang: 1

响应: 频道列表
```
