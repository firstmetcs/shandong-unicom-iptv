#coding:utf-8
import os
from Crypto.Cipher import DES3
from Crypto.Util.Padding import pad, unpad

# ====================== 完美绕过 3DES 退化校验版 ======================
class prpcrypt():
    def __init__(self, key):
        # 电信IPTV固定规则：8位密钥 → 重复3次 = 24位（会触发退化校验）
        self.key = (key * 3).encode('utf-8')  # 8位 ×3 = 24位
        self.mode = DES3.MODE_ECB

    def encrypt(self, text):
        try:
            # 手动绕过退化校验：直接构造密钥，不使用库的安全检查
            from Crypto.Cipher import DES

            # 拆分成3段DES密钥
            k1 = self.key[:8]
            k2 = self.key[8:16]
            k3 = self.key[16:]

            des1 = DES.new(k1, DES.MODE_ECB)
            des2 = DES.new(k2, DES.MODE_ECB)
            des3 = DES.new(k3, DES.MODE_ECB)

            # 3DES = 加密 → 解密 → 加密
            data = text.encode('utf-8')
            data = pad(data, DES.block_size)

            out = des1.encrypt(data)
            out = des2.decrypt(out)
            out = des3.encrypt(out)

            return out.hex()
        except:
            return ""

    def decrypt(self, text):
        try:
            from Crypto.Cipher import DES

            k1 = self.key[:8]
            k2 = self.key[8:16]
            k3 = self.key[16:]

            des1 = DES.new(k1, DES.MODE_ECB)
            des2 = DES.new(k2, DES.MODE_ECB)
            des3 = DES.new(k3, DES.MODE_ECB)

            data = bytes.fromhex(text)
            out = des3.decrypt(data)
            out = des2.encrypt(out)
            out = des1.decrypt(out)

            return unpad(out, DES.block_size).decode('utf-8')
        except Exception as e:
            return ""



################################# 破解密钥 ###########################################
def find_key(Authenticator):
    keys = []
    while len(Authenticator) < 10:
        Authenticator = input('未配置Authenticator，请输入正确的Authenticator的值：')
    print('开始测试00000000-99999999所有八位数字')
    for x in range(100000000):
        key = str('%08d'%x)
        if x % 500000 == 0:
            print('已经搜索至：-- %s -- '%key)
        pc = prpcrypt('%s'%key)
        try:
            ee = pc.decrypt(Authenticator)
            if ee:
                infos = ee.split('$')
                infotxt = '  随机数:%s\n  TOKEN:%s\n  USERID:%s\n  STBID:%s\n  ip:%s\n  mac:%s\n  运营商:%s'%(infos[0],infos[1],infos[2],infos[3],infos[4],infos[5],infos[7]) if len(infos)>7 else ''
                printtxt = '找到key:%s,解密后为:%s\n%s'%(x,ee,infotxt)
                print(printtxt)
                keys.append(key)
        except Exception as e:
            pass

    with open(os.getcwd() +'/key.txt','w') as f:
        line = '%s\n共找到KEY：%s个,分别为：%s\n'%(date_now,len(keys),','.join(keys))
        f.write(line)
    print('解密完成！共查找到 %s 个密钥：%s'%(len(keys),keys))

################################# 主程序入口 ###########################################
if __name__ == "__main__":
    find_key("C49C0C3288B2F5547EBABEFB97D4F3EA835DC2A7F244DD82E99544C384485970087562C440F93205602403196D199ADC70DF82AE8D8375EB4F333D25B1549DEC865B4F09548884999D34CD7E659CF30924A613BD306F75997768B0B496A935E4A8171D")
