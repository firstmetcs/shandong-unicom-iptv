import netifaces as ni

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


if __name__ == "__main__":
    local_ip = get_ip_by_interface('eth0')
    print(local_ip)
