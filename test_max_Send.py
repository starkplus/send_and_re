import socket
import struct
import time
import random
from RTP import RTPClient, PayloadType
import numpy as np
from collections import deque

# 配置
SERVER_IP = "127.0.0.1"  # 接收方IP地址
SERVER_PORT = 5500         # 接收方RTP端口

CLIENT_IP = "127.0.0.1"  # 本地发送IP地址
CLIENT_PORT = 5501          # 本地发送端口

DEVICE_ID = 12222222
TEST_DURATION = 30  # 测试持续时间(秒)

# 定义RTP的有效载荷类型
ASSOCIATED_PAYLOAD = {
    0: PayloadType.PCMU,
}

# 创建RTP数据包 - 保持原函数不变
def create_rtp_packet(version, padding, extension, csrc_count, marker, payload_type, sequence_number, timestamp, ssrc, packet_number, sample_rate, channels, device_id, audio_data):
    first_byte = (version << 6) | (padding << 5) | (extension << 4) | csrc_count
    second_byte = (marker << 7) | payload_type
    rtp_header = struct.pack(">B B H I I", first_byte, second_byte, sequence_number, timestamp, ssrc)
    custom_header = struct.pack(">I I B I", packet_number, sample_rate, channels, device_id)
    return rtp_header + custom_header + audio_data

def main():
    # 初始化UDP套接字
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((CLIENT_IP, CLIENT_PORT))
    
    # 预生成音频数据 - 与原代码相同
    sampling_rate = 96000
    frequency = 4400
    duration = 0.1
    samples = np.arange(duration * sampling_rate)
    waveform = np.sin(2 * np.pi * frequency * samples / sampling_rate)
    waveform_int16 = np.int16(waveform * 32767)
    channels = 4
    interleaved_waveform = []
    
    for sample in waveform_int16:
        interleaved_waveform.extend([sample] * channels)
    interleaved_waveform = np.array(interleaved_waveform, dtype=np.int16)
    audio_data = interleaved_waveform[:512].tobytes()
    
    # 启动发送测试
    try:
        print("开始测试最大发送速率...")
        version = 2
        padding = 0
        extension = 0
        csrc_count = 0
        marker = 0
        payload_type = 0
        sequence_number = 1
        timestamp = 123456
        ssrc = 654321
        packet_number = 1
        sample_rate = 96000
        channels = 4
        device_id = DEVICE_ID
        
        # 统计变量
        start_time = time.time()
        sent_packets = 0
        report_interval = 0.5  # 每0.5秒报告一次
        next_report_time = start_time + report_interval
        
        # 存储最近10个采样点的速率，用于计算平均值和稳定性
        recent_rates = deque(maxlen=10)
        end_time = start_time + TEST_DURATION
        
        print(f"测试将持续{TEST_DURATION}秒...")
        
        # 无休眠循环，以最快速度发送
        while time.time() < end_time:
            # 创建并发送数据包
            rtp_packet = create_rtp_packet(version, padding, extension, csrc_count, marker, 
                                          payload_type, sequence_number, timestamp, ssrc, 
                                          packet_number, sample_rate, channels, device_id, 
                                          audio_data)
            
            sock.sendto(rtp_packet, (SERVER_IP, SERVER_PORT))
            
            sent_packets += 1
            packet_number += 1
            sequence_number = (sequence_number + 1) % 65536  # 防止溢出
            timestamp += len(audio_data)
            
            # 检查是否需要输出统计信息
            current_time = time.time()
            if current_time >= next_report_time:
                elapsed = current_time - start_time
                rate = sent_packets / elapsed
                recent_rates.append(rate)
                print(f"已发送 {sent_packets} 个包，用时 {elapsed:.2f} 秒，当前速率: {rate:.2f} 包/秒")
                
                # 如果有足够的样本，显示平均速率
                if len(recent_rates) >= 5:
                    avg_rate = sum(recent_rates) / len(recent_rates)
                    print(f"最近平均速率: {avg_rate:.2f} 包/秒")
                
                next_report_time = current_time + report_interval

        # 测试结束
        final_elapsed = time.time() - start_time
        final_rate = sent_packets / final_elapsed
        print("\n测试完成!")
        print(f"总计发送 {sent_packets} 个包，用时 {final_elapsed:.2f} 秒")
        print(f"整体平均发送速率: {final_rate:.2f} 包/秒")
        print(f"最大稳定发送速率约为: {sum(recent_rates)/len(recent_rates):.2f} 包/秒")
        
    except KeyboardInterrupt:
        # 如果提前终止测试
        final_elapsed = time.time() - start_time
        final_rate = sent_packets / final_elapsed
        print("\n测试被手动终止!")
        print(f"总计发送 {sent_packets} 个包，用时 {final_elapsed:.2f} 秒")
        print(f"整体平均发送速率: {final_rate:.2f} 包/秒")
        if len(recent_rates) > 0:
            print(f"最近平均发送速率: {sum(recent_rates)/len(recent_rates):.2f} 包/秒")
    finally:
        sock.close()
        
if __name__ == "__main__":
    main()