import socket
import struct
import time
import random
from RTP import RTPClient, PayloadType
import numpy as np

# 配置
SERVER_IP = "127.0.0.1"  # 接收方IP地址
SERVER_PORT = 5500         # 接收方RTP端口

CLIENT_IP = "127.0.0.1"  # 本地发送IP地址
CLIENT_PORT = 5501          # 本地发送端口

DEVICE_ID = 12222222
TARGET_RATE = 750  # 目标每秒发送包数

# 定义RTP的有效载荷类型
ASSOCIATED_PAYLOAD = {
    0: PayloadType.PCMU,
}

# 创建RTP数据包
def create_rtp_packet(version, padding, extension, csrc_count, marker, payload_type, sequence_number, timestamp, ssrc, packet_number, sample_rate, channels, device_id, audio_data):
    # 设备包头结构：
    # 版本（2位） + 填充（1位） + 扩展（1位） + CSRC计数（4位）
    first_byte = (version << 6) | (padding << 5) | (extension << 4) | csrc_count
    # 标记（1位） + 负载类型（7位）
    second_byte = (marker << 7) | payload_type
    # 打包标准RTP包头（12字节）
    rtp_header = struct.pack(">B B H I I", first_byte, second_byte, sequence_number, timestamp, ssrc)
    
    # 打包自定义包头（包号（4字节） + 音频采样率（4字节） + 通道数（1字节） + 设备ID号（4字节））
    custom_header = struct.pack(">I I B I", packet_number, sample_rate, channels, device_id)
    return rtp_header + custom_header + audio_data

def main():
    # 初始化UDP套接字
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((CLIENT_IP, CLIENT_PORT))
    
    # 预生成音频数据
    sampling_rate = 96000  # 采样率
    frequency = 4400  # 正弦波频率
    duration = 0.1  # 持续时间（秒）
    samples = np.arange(duration * sampling_rate)  # 采样点索引
    waveform = np.sin(2 * np.pi * frequency * samples / sampling_rate)  # 正弦波
    waveform_int16 = np.int16(waveform * 32767)  # 将振幅缩放到 16 位范围内
    channels = 4  # 四通道
    interleaved_waveform = []
    
    for sample in waveform_int16:
        # 对每个样本重复填充到四个通道
        interleaved_waveform.extend([sample] * channels)
    interleaved_waveform = np.array(interleaved_waveform, dtype=np.int16)
    audio_data = interleaved_waveform[:512].tobytes()
    
    # 启动发送
    try:
        print(f"开始发送RTP数据，目标速率：{TARGET_RATE}包/秒...")
        version = 2
        padding = 0
        extension = 0
        csrc_count = 0
        marker = 0
        payload_type = 0  # 例如，PCMU
        sequence_number = 1
        timestamp = 123456
        ssrc = 654321
        packet_number = 1
        sample_rate = 96000
        channels = 4        # 四声道
        device_id = DEVICE_ID
        
        # 用于统计发送速率
        start_time = time.time()
        sent_packets = 0
        report_interval = 1.0  # 每1秒报告一次
        next_report_time = start_time + report_interval
        
        # 设置睡眠时间的上下限
        MIN_SLEEP = 0.000001  # 最小睡眠时间
        MAX_SLEEP = 0.01      # 最大睡眠时间(约100包/秒的基础速率)
        
        # 初始睡眠时间，从小一点开始，让系统逐渐找到平衡点
        adaptive_sleep = 0.0005  # 初始睡眠时间

        # 速率稳定器，记录最近的速率以避免过度调整
        recent_rates = []
        max_recent = 5  # 记录最近5个速率值
        
        # 避免频繁小调整的计数器
        stable_count = 0
        
        while True:
            # 创建RTP数据包
            rtp_packet = create_rtp_packet(version, padding, extension, csrc_count, marker, 
                                          payload_type, sequence_number, timestamp, ssrc, 
                                          packet_number, sample_rate, channels, device_id, 
                                          audio_data)
            
            # 发送数据包并记录时间
            send_start = time.perf_counter()
            sock.sendto(rtp_packet, (SERVER_IP, SERVER_PORT))
            send_end = time.perf_counter()
            
            sent_packets += 1
            packet_number += 1
            sequence_number = (sequence_number + 1) % 65536  # 防止溢出
            timestamp += len(audio_data)
            
            # 检查是否需要输出统计信息
            current_time = time.time()
            if current_time >= next_report_time:
                elapsed = current_time - start_time
                rate = sent_packets / elapsed
                
                # 记录最近的速率
                recent_rates.append(rate)
                if len(recent_rates) > max_recent:
                    recent_rates.pop(0)
                
                # 计算平均速率以避免过度响应短期波动
                avg_rate = sum(recent_rates) / len(recent_rates) if recent_rates else rate
                
                # 计算距离目标的百分比差异
                deviation = abs(avg_rate - TARGET_RATE) / TARGET_RATE
                
                # 显示当前状态
                print(f"用时 {elapsed:.2f} 秒，速率 {rate:.2f} 包/秒，平均 {avg_rate:.2f} 包/秒，休眠时间 {adaptive_sleep:.8f}秒")
                
                # 多级调整策略
                if abs(avg_rate - TARGET_RATE) < TARGET_RATE * 0.03:  # 在目标3%范围内
                    stable_count += 1
                    # 已经稳定，每3次报告才调整一次，减少波动
                    if stable_count >= 3:
                        if avg_rate > TARGET_RATE*1.05:
                            adaptive_sleep *= 1.01  # 微调增加1%
                        elif avg_rate < TARGET_RATE*0.95:
                            adaptive_sleep *= 0.99  # 微调减少1%
                        stable_count = 0  # 重置计数器
                else:
                    stable_count = 0  # 不稳定，重置计数器
                    
                    if avg_rate > TARGET_RATE*1.05:  # 速率过高
                        if deviation > 0.20:  # 偏离超过20%
                            adaptive_sleep *= 1.20  # 快速增加20%
                        elif deviation > 0.10:  # 偏离10-20%
                            adaptive_sleep *= 1.10  # 中等增加10%
                        elif deviation > 0.05:  # 偏离5-10%
                            adaptive_sleep *= 1.05  # 小幅增加5%
                        else:  # 偏离3-5%
                            adaptive_sleep *= 1.03  # 微调增加3%
                    elif avg_rate < TARGET_RATE*0.95:  # 速率过低
                        if deviation > 0.20:  # 偏离超过20%
                            adaptive_sleep *= 0.80  # 快速减少20%
                        elif deviation > 0.10:  # 偏离10-20%
                            adaptive_sleep *= 0.90  # 中等减少10%
                        elif deviation > 0.05:  # 偏离5-10%
                            adaptive_sleep *= 0.95  # 小幅减少5% 
                        else:  # 偏离3-5%
                            adaptive_sleep *= 0.97  # 微调减少3%
                
                # 确保休眠时间在合理范围内
                adaptive_sleep = max(MIN_SLEEP, min(MAX_SLEEP, adaptive_sleep))
                
                next_report_time = current_time + report_interval
            
            # 计算本次发送操作花费的时间
            processing_time = send_end - send_start
            # 动态调整休眠时间，确保总体处理+休眠约为目标速率的倒数
            sleep_time = max(0, adaptive_sleep - processing_time)
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        # 最终统计
        final_elapsed = time.time() - start_time
        final_rate = sent_packets / final_elapsed
        print(f"\n发送终止")
        print(f"总计发送 {sent_packets} 个包，用时 {final_elapsed:.2f} 秒")
        print(f"平均发送速率: {final_rate:.2f} 包/秒")
        print(f"目标速率: {TARGET_RATE} 包/秒")
        print(f"实际速率与目标速率比例: {(final_rate/TARGET_RATE)*100:.2f}%")
    finally:
        sock.close()
        
if __name__ == "__main__":
    main()