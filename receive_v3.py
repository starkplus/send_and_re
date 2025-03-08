import socket
import struct
import os
import wave
import time
from RTP import RTPClient, PayloadType

# 配置
SERVER_IP = "127.0.0.1"  # 本地接收IP地址
SERVER_PORT = 5500          # RTP接收端口
OUTPUT_DIR = "./output/"    # 输出目录

CLIENT_IP = "127.0.0.1"  # 发送方IP地址
CLIENT_PORT = 5501          # 发送方RTP端口

DEVICE_ID = 12222222
SAVE_THRESHOLD = 750  # 每750个包保存一次

# 定义RTP的有效载荷类型
ASSOCIATED_PAYLOAD = {
    0: PayloadType.PCMU,
}

# 创建输出目录（如果不存在）
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)


# 处理并保存音频数据
def save_audio(buffer, package_number, sample_rate, channels):
    data = b''.join(buffer)
    # 保存为PCM文件
    pcm_file_path = f"{OUTPUT_DIR}audio_{package_number}.pcm"
    with open(pcm_file_path, "wb") as f:
        f.write(data)
    print(f"音频数据已保存为 PCM 文件: {pcm_file_path}")

    # 保存为WAV文件
    wav_file_path = f"{OUTPUT_DIR}audio_{package_number}.wav"
    with wave.open(wav_file_path, "wb") as wf:
        # 设置WAV文件的参数
        wf.setnchannels(channels)          # 通道数
        wf.setsampwidth(2)                 # 位深，PCM 8位通常为1，16位为2
        wf.setframerate(sample_rate)       # 采样率
        wf.writeframes(data)               # 写入音频数据
    print(f"音频数据已保存为 WAV 文件: {wav_file_path}")

# 解析RTP数据包（根据设备定义）
def parse_rtp_packet(rtp_data):
    if len(rtp_data) != 1037 + 12:  # 加上RTP包头12字节
        print(f"数据包长度异常: {len(rtp_data)}")
        return None
    
    # 跳过12字节RTP包头
    rtp_data = rtp_data[12:]
    
    # 解包数据（包号 + 采样率 + 通道数 + 设备ID号 + 音频数据）
    packet_number, sample_rate, channels, device_id = struct.unpack(">I I B I", rtp_data[:13])
    
    # 音频数据部分
    audio_data = rtp_data[13:]
    
    return packet_number, sample_rate, channels, device_id, audio_data

def main():
    # 初始化RTP客户端
    rtp_client = RTPClient(
        assoc=ASSOCIATED_PAYLOAD,
        inIP=SERVER_IP,
        inPort=SERVER_PORT,
        outIP=CLIENT_IP,
        outPort=CLIENT_PORT,
        sendrecv="recvonly"
    )

    # 启动接收
    rtp_client.start()

    packet_counter = 0  # 用于标记包数
    buffer = []  # 用于缓存包
    
    # 添加接收速率监控
    receive_start_time = time.time()
    total_received = 0
    report_interval = 1.0  # 每秒报告一次
    next_report_time = receive_start_time + report_interval
    
    # 用于计算滑动窗口速率
    recent_rates = []
    max_recent_count = 5
    
    # 存储性能监控
    last_save_time = None
    save_times = []

    try:
        print("开始接收RTP数据...")
        while True:                               
            # 读取RTP数据包
            rtp_data, addr = rtp_client.recv()
            if not rtp_data:
                time.sleep(0.01)  # 没有数据时短暂休眠
                continue
            
            # 成功接收到一个包
            total_received += 1
            
            # 解析数据包（根据设备结构）
            packet_info = parse_rtp_packet(rtp_data)
            if packet_info is None:
                continue  # 如果包解析失败，跳过处理

            packet_number, sample_rate, channels, device_id, audio_data = packet_info
            
            # 这里只处理来自ID为12222222的数据包
            if device_id != DEVICE_ID:
                continue  # 如果设备ID不匹配，则跳过
                
            # 处理有效的数据包
            buffer.append(audio_data)
            packet_counter += 1
            
            # 检查是否需要报告接收速率
            current_time = time.time()
            if current_time >= next_report_time:
                elapsed = current_time - receive_start_time
                rate = total_received / elapsed
                
                # 保存最近的速率
                recent_rates.append(rate)
                if len(recent_rates) > max_recent_count:
                    recent_rates.pop(0)
                
                # 计算平均速率
                avg_rate = sum(recent_rates) / len(recent_rates) if recent_rates else rate
                
                # 输出接收统计
                print(f"接收速率: {rate:.2f} 包/秒 (平均: {avg_rate:.2f}, 累计接收: {total_received} 包, 当前缓冲: {packet_counter} 包)")
                
                # 如果有存储时间记录，显示平均存储时间
                if save_times:
                    avg_save_time = sum(save_times) / len(save_times)
                    print(f"平均存储时间: {avg_save_time:.4f} 秒/批次")
                
                next_report_time = current_time + report_interval
            
            # 检查是否需要保存
            if packet_counter >= SAVE_THRESHOLD:
                save_start = time.time()
                
                # 将缓冲区的数据写入保存函数
                save_audio(buffer, packet_number, sample_rate, channels)
                
                save_end = time.time()
                save_duration = save_end - save_start
                save_times.append(save_duration)
                if len(save_times) > 10:  # 只保留最近10次存储时间
                    save_times.pop(0)
                
                print(f"保存 {packet_counter} 包用时: {save_duration:.4f} 秒, "
                      f"接收时间: {save_start - (last_save_time if last_save_time else receive_start_time):.2f} 秒")
                
                last_save_time = save_end
                
                # 清空缓冲区
                buffer.clear()
                # 重置包计数器
                packet_counter = 0
                
    except KeyboardInterrupt:
        print("接收终止")
        
        # 显示最终统计信息
        final_elapsed = time.time() - receive_start_time
        final_rate = total_received / final_elapsed if final_elapsed > 0 else 0
        print(f"总计接收 {total_received} 个包，用时 {final_elapsed:.2f} 秒")
        print(f"平均接收速率: {final_rate:.2f} 包/秒")
        
    finally:
        rtp_client.stop()

if __name__ == "__main__":
    main()