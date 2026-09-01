import sys
import random
import re
import time
import socket
import uuid
from Crypto.Cipher import DES
from Crypto.Util.Padding import pad
from urllib.parse import urlparse
import requests
import netifaces as ni
from requests_toolbelt.adapters import source

CONFIG = {
    # 破解得到的密钥
    'key': '',
    'user_id': '',
    'stb_id': '',
    'mac': '',
    'ip': None,  # 自动获取
    'stb_type': '',
    'stb_version': '',
    # 服务器地址
    'eds_server': '', 
    'platform': 'CTC', 
    'interface_suffix': 'CU', 
}

tv_channel_name = {
    "CCTV-1综合": "CCTV-1",
    "CCTV-2财经": "CCTV-2",
    "CCTV-3综艺": "CCTV-3",
    "CCTV-4中文国际": "CCTV-4",
    "CCTV-5体育": "CCTV-5",
    "CCTV-5+体育赛事": "CCTV-5+",
    "CCTV-6电影": "CCTV-6",
    "CCTV-7国防军事": "CCTV-7",
    "CCTV-8电视剧": "CCTV-8",
    "CCTV-9纪录": "CCTV-9",
    "CCTV-10科教": "CCTV-10",
    "CCTV-11戏曲": "CCTV-11",
    "CCTV-12社会与法": "CCTV-12",
    "CCTV-13新闻": "CCTV-13",
    "CCTV-14少儿": "CCTV-14",
    "CCTV-15音乐": "CCTV-15",
    "CGTN英语": "CGTN",
    "山东教育卫视": "山东教育",
    "山西卫视-标清": "山西卫视",
    "优漫卡通-标清": "优漫卡通",
    "嘉佳卡通-标清": "嘉佳卡通",
    "农林卫视-标清": "农林卫视",
    "厦门卫视-标清": "厦门卫视",
    "中国教育-1": "中国教育1",
    "中国教育-2-标清": "中国教育2",
    "中国教育-4": "中国教育4",
    "延边卫视-标清": "延边卫视",
    "爱体育高清": "爱体育",
    "IPTV谍战剧场": "谍战剧场",
    "CCTV-17农业农村": "CCTV-17",
    "三沙卫视-标清": "三沙卫视",
    "发现之旅-标清": "发现之旅",
    "中学生-标清": "中学生",
    "老故事-标清": "老故事",
    "CCTV4中文国际欧洲": "CCTV4欧洲",
    "CCTV4中文国际美洲": "CCTV4美洲",
    "CGTN英文纪录": "CGTN纪录",
    "CGTN西班牙语": "CGTN西语",
    "CGTN阿拉伯语": "CGTN阿语",
    "CCTV-4K超高清": "CCTV4K",
    "CHC-家庭影院": "CHC家庭影院",
    "CHC-动作电影": "CHC动作电影",
    "CHC-影迷电影": "CHC影迷电影",
    "书画-标清": "书画",
    "新动漫-标清": "新动漫",
    "IPTV收视指南": "收视指南",
    "IPTV相声小品": "相声小品",
    "优优宝贝-标清": "优优宝贝",
    "北京卫视4K超高清": "北京卫视4K",
    "深圳卫视4K超高清": "深圳卫视4K",
    "广东卫视4K超高清": "广东卫视4K",
    "山东卫视4K超高清": "山东卫视4K",
    "湖南卫视4K超高清": "湖南卫视4K",
    "浙江卫视4K超高清": "浙江卫视4K",
    "江苏卫视4K超高清": "江苏卫视4K",
    "东方卫视4K超高清": "东方卫视4K",
    "四川卫视4K超高清": "四川卫视4K",
    "金鹰卡通-标清": "金鹰卡通",
    "汽摩频道": "汽摩",
    "优购物-标清": "优购物",
    "央广购物-标清": "央广购物",
    "浙江卫视-标清": "浙江卫视",
    "安徽卫视-标清": "安徽卫视",
    "北京卫视-标清": "北京卫视",
    "东方卫视-标清": "东方卫视",
    "天津卫视-标清": "天津卫视",
    "辽宁卫视-标清": "辽宁卫视",
    "东南卫视-标清": "东南卫视",
    "湖北卫视-标清": "湖北卫视",
}

# 传入网卡名，比如 'eth0' 或 'en0'
def get_ip_by_interface(interface_name):
    try:
        addr_info = ni.ifaddresses(interface_name)
        # 获取 IPv4 地址
        ip = addr_info[ni.AF_INET][0]['addr']
        return ip
    except Exception as e:
        print(f"无法获取网卡 {interface_name} 的IP: {e}")
        return None


save_dir_m3u = 'playlist.m3u'

def get_local_ip():
    try:
        # s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # s.connect(('8.8.8.8', 80))
        # local_ip = s.getsockname()[0]
        # s.close()
        local_ip = get_ip_by_interface('eth0')
        return local_ip
    except:
        pass
    try:
        hostname = socket.gethostname()
        return socket.gethostbyname(hostname)
    except:
        pass
    return None


def auto_detect_config():
    print("=" * 60)
    print("配置信息")
    print("=" * 60)
    print()
    # 检测IP
    if CONFIG['ip'] is None:
        print("检测IP地址...")
        local_ip = get_local_ip()
        if local_ip:
            CONFIG['ip'] = local_ip
            print(f" [OK] 使用本机IP: {local_ip}")
            if local_ip.startswith('10.'):
                print(f" [OK] 在IPTV网段 (10.x.x.x)")
            else:
                print(f" [!] 不在IPTV网段，可能需要配置IPTV接口")
        else:
            print(" [X] 无法获取IP地址")
            return False
    print()
    print("最终配置:")
    print(f" IP: {CONFIG['ip']} (自动获取)")
    print(f" MAC: {CONFIG['mac']} (固定配置)")
    print(f" 平台标识: {CONFIG['platform']} (用于明文)")
    print(f" 接口后缀: HW{CONFIG['interface_suffix']} (用于URL)")
    print()
    return True

class IPTVAuthenticator:
    """IPTV认证器"""
    def __init__(self, config):
        self.config = config
        # 1. 创建指定网卡IP的适配器（传入该网卡在当前机器上的IP地址）
        # 填入你的目标网卡 IP，端口写 0 表示由系统随机分配高位端口
        adapter = source.SourceAddressAdapter(CONFIG['ip'])

        # 2. 创建 Session 并绑定 http 和 https
        self.session = requests.Session()
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        self.epg_host = None
        self.user_token = None
        self.cookies = None
        self.stbid = None

    def log(self, msg):
        """日志输出"""
        try:
            print(f"[{time.strftime('%H:%M:%S')}] {msg}")
        except:
            print(f"[{time.strftime('%H:%M:%S')}] {msg.encode('gbk', errors='ignore').decode('gbk')}")

    def generate_authenticator(self, encrypt_token):
        """生成Authenticator"""
        # 生成8位随机数
        random_num = random.randint(10000000, 99999999)
        # 组装明文 - 关键修改：用"Reserved"代替空，使用CTC平台标识
        plaintext = f"{random_num}${encrypt_token}${self.config['user_id']}${self.config['stb_id']}${self.config['ip']}${self.config['mac']}$Reserved$CTC"
        # DES加密（3DES退化为DES）
        key = self.config['key'].encode('ascii')
        cipher = DES.new(key, DES.MODE_ECB)
        padded = pad(plaintext.encode('ascii'), 8)
        authenticator = cipher.encrypt(padded).hex().upper()
        self.log(f"生成Authenticator成功 (Random: {random_num})")
        self.log(f"明文格式: {plaintext}")
        return authenticator

    def step1_authentication_url(self):
        """步骤1: 访问AuthenticationURL获取EPG服务器"""
        self.log("=" * 60)
        self.log("步骤1: 访问AuthenticationURL")
        self.log("=" * 60)
        url = f"http://{self.config['eds_server']}/EDS/jsp/AuthenticationURL?UserID={self.config['user_id']}&Action=Login&FCCSupport=1"
        headers = {
            'User-Agent': 'B700-V2A|Mozilla|5.0|ztebw(Chrome)|1.2.0',
        }
        self.log(f"请求: {url}")
        try:
            res = self.session.get(url,headers = headers,timeout = 10)
            # 提取EPG服务器地址
            self.epg_host = urlparse(res.url).netloc
            self.log(f"[OK] EPG服务器: {self.epg_host}")
            return True
        except Exception as e:
            self.log(f"[X] 失败: {e}")
            return False

    def step2_auth_login(self):
        """步骤2: 提交authLogin获取EncryptToken"""
        self.log("=" * 60)
        self.log("步骤2: 提交authLogin")
        self.log("=" * 60)
        url = f"http://{self.epg_host}/EPG/jsp/authLoginHW{self.config['interface_suffix']}.jsp"
        data = {
            'UserID': self.config['user_id'],
            'VIP': ''
        }

        headers = {
            'User-Agent': 'B700-V2A|Mozilla|5.0|ztebw(Chrome)|1.2.0',
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        self.log(f"请求: {url}")
        try:
            res = self.session.post(url, headers = headers, data = data,timeout = 10)
            res.encoding = 'utf-8'
            html = res.text
            # 提取EncryptToken
            match = re.search(r'EncryptToken\s*=\s*"([^"]+)"', html)
            if match:
                encrypt_token = match.group(1)
                self.log(f"[OK] EncryptToken: {encrypt_token}")
                return encrypt_token
            else:
                self.log("[X] 未找到EncryptToken")
                return None
        except Exception as e:
            self.log(f"[X] 失败: {e}")
            return None

    def step3_valid_authentication(self, encrypt_token):
        """步骤3: 提交ValidAuthentication获取Session"""
        self.log("=" * 60)
        self.log("步骤3: 提交ValidAuthentication")
        self.log("=" * 60)
        url = f"http://{self.epg_host}/EPG/jsp/ValidAuthenticationHW{self.config['interface_suffix']}.jsp"
        # 生成Authenticator
        authenticator = self.generate_authenticator(encrypt_token)
        data = {
            'UserID': self.config['user_id'],
            'Lang': '1',
            'SupportHD': '1',
            'NetUserID': 'SDIPTVPPPOE@sdiptv',
            'Authenticator': authenticator,
            'STBType': self.config['stb_type'],
            'STBVersion': self.config['stb_version'],
            'conntype': 'dhcp',
            'STBID': self.config['stb_id'],
            'templateName': '',
            'areaId': '',
            'userToken': encrypt_token,
            'userGroupId': '',
            'productPackageId': '',
            'mac': self.config['mac'],
            'UserField': '',
            'SoftwareVersion': self.config['stb_version'],
            'IsSmartStb': 'undefined',
            'desktopId': 'undefined',
            'stbmaker': '',
            'VIP': ''
        }

        headers = {
            'User-Agent': 'B700-V2A|Mozilla|5.0|ztebw(Chrome)|1.2.0',
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        self.log(f"请求: {url}")
        try:
            res = self.session.post(url, headers=headers, data=data, timeout=10)
            res.encoding = 'utf-8'

            html = res.text
            self.cookies = res.cookies
            
            # 提取UserToken和stbid
            match = re.search(r'"UserToken"\s+value="([^"]+)"', html)
            if match:
                self.user_token = match.group(1)
                self.log(f"[OK] UserToken: {self.user_token}")

            match = re.search(r'"stbid"\s+value="([^"]+)"', html)
            if match:
                self.stbid = match.group(1)
                self.log(f"[OK] stbid: {self.stbid}")

            if self.cookies and self.user_token:
                return True
            else:
                self.log("[X] 未获取到Session信息")
                return False
        except Exception as e:
            self.log(f"[X] 失败: {e}")
            return False

    def step4_get_channel_list(self):
        """步骤4: 获取频道列表"""
        self.log("=" * 60)
        self.log("步骤4: 获取频道列表")
        self.log("=" * 60)
        url = f"http://{self.epg_host}/EPG/jsp/getchannellistHW{self.config['interface_suffix']}.jsp"
        data = {
            'conntype': 'dhcp',
            'UserToken': self.user_token,
            'stbid': self.stbid,
            'SupportHD': '1',
            'UserID': self.config['user_id'],
            'Lang': '1'
        }
        self.log(f"请求: {url}")
        try:
            res = self.session.post(url, data=data, cookies=self.cookies, timeout=10)
            res.encoding = 'utf-8'
            html = res.text

            # 生成m3u
            matches = self.step4_1_generate_m3u(html)
            # return matches
            
            # # 仅保存原始响应到文件
            with open('getchannellistHWCU_raw.jsp', 'w', encoding='utf-8') as f:
                f.write(html)
            self.log(f"[OK] 原始响应已保存到 getchannellistHWCU_raw.jsp")

            # 仅解析数量用于提示，不做其他保存和打印
            pattern = r'ChannelID="([^"]+)",ChannelName="([^"]+)",UserChannelID="([^"]+)",ChannelURL="([^"]+)"'
            matches = re.findall(pattern, html)
            return len(matches)
        except Exception as e:
            self.log(f"[X] 失败: {e}")
            return None

    def step4_1_generate_m3u(self, html):
        """步骤4: 获取频道列表"""
        self.log("=" * 60)
        self.log("步骤4_1: 生成频道列表m3u")
        self.log("=" * 60)
        # 优化正则匹配（兼容更多格式）
        pattern = re.compile(
            r'ChannelID\=\"(\d+)\",'
            r'ChannelName\=\"(.+?)\",'
            r'UserChannelID\=\"(\d+)\",'
            r'ChannelURL=\"igmp://(.+?)\".+?'
            r'TimeShift\=\"(\d+)\",'
            r'TimeShiftLength\=\"(\d+)\".+?,'
            r'TimeShiftURL\=\"(.+?)\".+?'
            r'FCCEnable\=\"(\d+)\",'
            r'ChannelFCCIP=\"(.*?)\",'
            r'ChannelFCCPort=\"(.*?)\",'
            r'ChannelFECPort=\"(.*?)\"'
        )
        channels = pattern.findall(html)
        
        # 整理频道数据 + 生成频道ID映射（用于EPG）
        channel_list = []
        channel_info = {}  # key: ChannelID, value: [频道名称, UserChannelID]
        for ch in channels:
            channel_id, ch_name, user_ch_id, igmp, timeshift, ts_len, ts_url, fcc, fcc_ip, fcc_port, fec_port = ch

            channel_list.append([channel_id, ch_name, user_ch_id, igmp, timeshift, ts_len, ts_url, fcc, fcc_ip, fcc_port, fec_port])
            channel_info[channel_id] = [ch_name, user_ch_id]
        
        self.log(f'✅ 共获取有效频道数量：{len(channel_list)}')

        if not channels:
            self.log("❌ 未获取到任何频道")
            return 0


        # 生成M3U文件
        with open(save_dir_m3u, 'w', encoding='utf-8') as fm3u:
            logo = 'https://gh-proxy.com/https://raw.githubusercontent.com/firstmetcs/shandong-unicom-iptv/main/logo/'
            fm3u.write(f'#EXTM3U x-tvg-url="https://gh-proxy.com/https://raw.githubusercontent.com/plsy1/epg/main/e/seven-days.xml.gz"\n')
            for channel in channels:
                channel_id, ch_name, user_ch_id, igmp, timeshift, ts_len, ts_url, fcc, fcc_ip, fcc_port, fec_port = channel
                ch_name = tv_channel_name.get(ch_name, ch_name)
                # 支持时移的M3U标签
                url=f'rtp://{igmp}'
                m3u_ts = f' catchup="default" catchup-source="{ts_url}&playseek=${{(b)yyyyMMddHHmmss}}-${{(e)yyyyMMddHHmmss}}"' if ts_url else ""
                if fcc == "2" and fec_port == "0":
                    url = f"{url}?fcc={fcc_ip}:{fcc_port}"
                elif fcc == "0" and fec_port != "0":
                    url = f"{url}?fec={fec_port}"
                elif fcc == "2" and fec_port != "0":
                    url = f"{url}?fcc={fcc_ip}:{fcc_port}&fec={fec_port}"
                fm3u.write(f'#EXTINF:-1 tvg-id="{channel_id}" tvg-name="{ch_name}" tvg-logo="{logo}{ch_name}.png" {m3u_ts}, {ch_name}\n{url}\n')
        self.log(f"✅ 频道文件生成完成：- {save_dir_m3u}")

        return len(channel_list)


    def run(self):
        """运行完整认证流程"""
        print()
        print("=" * 60)
        print("山东联通华为IPTV认证流程")
        print("=" * 60)
        print(f"用户ID: {self.config['user_id']}")
        print(f"密钥: {self.config['key']}")
        print(f"平台标识: {self.config['platform']} (明文)")
        print(f"接口后缀: HW{self.config['interface_suffix']} (URL)")
        print(f"IP: {self.config['ip']}")
        print(f"MAC: {self.config['mac']}")
        print("=" * 60)
        print()

        # 步骤1
        if not self.step1_authentication_url():
            print('步骤1失败')
            return False

        # 步骤2
        encrypt_token = self.step2_auth_login()
        if not encrypt_token:
            print('步骤2失败')
            return False

        # 步骤3
        if not self.step3_valid_authentication(encrypt_token):
            print('步骤3失败')
            return False

        # 步骤4
        channel_count = self.step4_get_channel_list()
        if not channel_count:
            print('步骤4失败')
            return False

        # 输出结果
        print()
        print("=" * 60)
        print(f"[OK] 认证完成，频道数量: {channel_count}")
        print(f"[OK] 原始响应已保存到: getchannellistHWCU_raw.jsp")
        print("=" * 60)
        print()
        return True

def main():
    """主函数"""
    print("=" * 60)
    print(f"开始认证流程：{time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 自动检测配置
    if not auto_detect_config():
        print("配置检测失败，请手动配置")
        print()
        print("手动配置方法:")
        print(" 编辑脚本，设置CONFIG['ip']和CONFIG['mac']")
        print()
        # input("按回车键退出...")
        return

    try:
        auth = IPTVAuthenticator(CONFIG)
        success = auth.run()
        if success:
            # print("按回车键退出...")
            # input()
            sys.exit(0)
        else:
            print()
            print("认证失败!")
            # print("按回车键退出...")
            # input()
            sys.exit(1)
    except Exception as e:
        print(f"\n错误: {e}")
        # print("按回车键退出...")
        # input()
        sys.exit(1)

if __name__ == "__main__":
    main()
