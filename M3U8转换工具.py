import os
import re
import requests
import m3u8
import subprocess
import sys
from urllib.parse import urljoin, urlparse
import time

class M3U8Converter:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.ok_dir = os.path.join(self.base_dir, "OK")
        self.temp_dir = os.path.join(self.base_dir, "temp")
        self.create_directories()
        
    def create_directories(self):
        """创建必要的文件夹"""
        if not os.path.exists(self.ok_dir):
            os.makedirs(self.ok_dir)
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
    
    def clear_temp(self):
        """清理临时文件夹"""
        if os.path.exists(self.temp_dir):
            for file in os.listdir(self.temp_dir):
                file_path = os.path.join(self.temp_dir, file)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    print(f"清理临时文件失败: {e}")
    
    def show_help(self):
        """显示帮助信息"""
        help_text = """
==================== 错误代码说明 ====================
400 - 请求参数错误
401 - 访问被拒绝，需要认证
403 - 禁止访问，没有权限
404 - 资源不存在
408 - 请求超时
450 - 链接无法访问（网络问题或链接已失效）
451 - m3u8文件格式错误或无法解析
452 - 本地路径无法访问（文件不存在或无权限）
453 - 视频片段下载失败
454 - 视频合并失败
455 - 无效的用户输入
500 - 服务器内部错误
====================================================
"""
        print(help_text)
        input("\n按回车键返回主菜单...")
    
    def download_ts_segment(self, url, save_path, headers=None, max_retries=3):
        """下载单个TS片段，支持重试"""
        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=headers, timeout=30)
                if response.status_code == 200:
                    with open(save_path, 'wb') as f:
                        f.write(response.content)
                    return True
                else:
                    print(f"下载失败，状态码: {response.status_code}")
                    return False
            except requests.exceptions.RequestException as e:
                print(f"下载尝试 {attempt + 1}/{max_retries} 失败: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    return False
        return False
    
    def merge_ts_files(self, ts_files, output_path):
        """合并TS文件"""
        try:
            with open(output_path, 'wb') as outfile:
                for ts_file in ts_files:
                    if os.path.exists(ts_file):
                        with open(ts_file, 'rb') as infile:
                            outfile.write(infile.read())
                    else:
                        print(f"警告: 文件不存在 {ts_file}")
                        return False
            return True
        except Exception as e:
            print(f"合并文件时出错: {e}")
            return False
    
    def get_filename_from_url(self, url):
        """从URL获取文件名"""
        parsed = urlparse(url)
        path = parsed.path
        # 获取最后一个路径部分作为文件名
        filename = os.path.basename(path)
        if not filename or '.' not in filename:
            filename = "video"
        # 移除可能的查询参数
        filename = filename.split('?')[0]
        # 确保有扩展名
        if not filename.endswith('.mp4'):
            filename = filename.rsplit('.', 1)[0] if '.' in filename else filename
            filename += '.mp4'
        return filename
    
    def process_m3u8_url(self, m3u8_url):
        """处理网络m3u8链接"""
        print(f"\n开始处理: {m3u8_url}")
        
        try:
            # 下载m3u8文件
            response = requests.get(m3u8_url, timeout=30)
            if response.status_code != 200:
                print(f"错误 450: 无法访问链接 (HTTP {response.status_code})")
                return False
            
            # 解析m3u8内容
            try:
                m3u8_obj = m3u8.loads(response.text)
            except Exception as e:
                print(f"错误 451: m3u8文件格式错误 - {e}")
                return False
            
            # 获取基础URL
            base_url = m3u8_url[:m3u8_url.rfind('/') + 1]
            
            # 如果m3u8文件指向另一个m3u8文件（多码率适配）
            if m3u8_obj.is_variant:
                print("检测到多码率m3u8，选择第一个码率...")
                if m3u8_obj.playlists:
                    playlist_url = urljoin(base_url, m3u8_obj.playlists[0].uri)
                    return self.process_m3u8_url(playlist_url)
            
            # 获取TS片段列表
            ts_segments = []
            for segment in m3u8_obj.segments:
                if segment.uri.startswith('http'):
                    ts_url = segment.uri
                else:
                    ts_url = urljoin(base_url, segment.uri)
                ts_segments.append(ts_url)
            
            if not ts_segments:
                print("错误 451: 没有找到视频片段")
                return False
            
            print(f"找到 {len(ts_segments)} 个视频片段")
            
            # 下载所有TS片段
            downloaded_files = []
            for i, ts_url in enumerate(ts_segments):
                ts_filename = f"segment_{i:05d}.ts"
                ts_path = os.path.join(self.temp_dir, ts_filename)
                
                print(f"下载片段 {i+1}/{len(ts_segments)}...")
                if self.download_ts_segment(ts_url, ts_path):
                    downloaded_files.append(ts_path)
                else:
                    print(f"错误 453: 片段 {i+1} 下载失败")
                    return False
            
            # 生成输出文件名
            output_filename = self.get_filename_from_url(m3u8_url)
            output_path = os.path.join(self.ok_dir, output_filename)
            
            # 合并TS文件
            print("正在合并视频片段...")
            if self.merge_ts_files(downloaded_files, output_path):
                print(f"\n✓ 转换完成!")
                print(f"文件已保存到: {output_path}")
                return True
            else:
                print("错误 454: 视频合并失败")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"错误 450: 网络请求失败 - {e}")
            return False
        except Exception as e:
            print(f"未知错误: {e}")
            return False
    
    def process_local_m3u8(self, file_path):
        """处理本地m3u8文件"""
        print(f"\n开始处理本地文件: {file_path}")
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            print("错误 452: 本地路径无法访问，文件不存在")
            return False
        
        try:
            # 读取m3u8文件
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析m3u8
            try:
                m3u8_obj = m3u8.loads(content)
            except Exception as e:
                print(f"错误 451: m3u8文件格式错误 - {e}")
                return False
            
            # 获取基础路径
            base_dir = os.path.dirname(file_path)
            
            # 获取TS片段列表
            ts_segments = []
            for segment in m3u8_obj.segments:
                if segment.uri.startswith(('http://', 'https://')):
                    ts_segments.append(segment.uri)
                else:
                    # 处理相对路径
                    ts_path = os.path.join(base_dir, segment.uri)
                    ts_segments.append(ts_path)
            
            if not ts_segments:
                print("错误 451: 没有找到视频片段")
                return False
            
            print(f"找到 {len(ts_segments)} 个视频片段")
            
            # 下载/复制所有TS片段
            downloaded_files = []
            for i, ts_source in enumerate(ts_segments):
                ts_filename = f"segment_{i:05d}.ts"
                ts_path = os.path.join(self.temp_dir, ts_filename)
                
                print(f"处理片段 {i+1}/{len(ts_segments)}...")
                
                if ts_source.startswith(('http://', 'https://')):
                    # 网络片段
                    if self.download_ts_segment(ts_source, ts_path):
                        downloaded_files.append(ts_path)
                    else:
                        print(f"错误 453: 片段 {i+1} 下载失败")
                        return False
                else:
                    # 本地片段
                    if os.path.exists(ts_source):
                        import shutil
                        shutil.copy2(ts_source, ts_path)
                        downloaded_files.append(ts_path)
                    else:
                        print(f"错误 452: 本地片段不存在 - {ts_source}")
                        return False
            
            # 生成输出文件名
            base_filename = os.path.splitext(os.path.basename(file_path))[0]
            output_path = os.path.join(base_dir, f"{base_filename}.mp4")
            
            # 合并TS文件
            print("正在合并视频片段...")
            if self.merge_ts_files(downloaded_files, output_path):
                print(f"\n✓ 转换完成!")
                print(f"文件已保存到: {output_path}")
                return True
            else:
                print("错误 454: 视频合并失败")
                return False
                
        except Exception as e:
            print(f"未知错误: {e}")
            return False
    
    def main_menu(self):
        """主菜单"""
        while True:
            # 清理屏幕（根据不同系统）
            os.system('cls' if os.name == 'nt' else 'clear')
            
            print("\n" + "="*50)
            print("          M3U8 视频转换工具")
            print("="*50)
            print("1. 网络链接转换")
            print("2. 本地 m3u8 文件转换")
            print("3. 退出")
            print("4. 帮助")
            print("="*50)
            
            choice = input("\n请选择操作 (1-4): ").strip()
            
            if choice == '1':
                self.network_conversion()
            elif choice == '2':
                self.local_conversion()
            elif choice == '3':
                print("\n感谢使用，再见！")
                self.clear_temp()
                sys.exit(0)
            elif choice == '4':
                self.show_help()
            else:
                print("\n错误 455: 无效的选择，请重新输入")
                input("按回车键继续...")
    
    def network_conversion(self):
        """网络链接转换流程"""
        print("\n" + "-"*50)
        print("网络链接转换")
        print("-"*50)
        
        m3u8_url = input("请输入 m3u8 网络链接: ").strip()
        
        if not m3u8_url:
            print("\n错误 455: 链接不能为空")
            input("按回车键返回主菜单...")
            return
        
        # 验证URL格式
        if not m3u8_url.startswith(('http://', 'https://')):
            print("\n错误 455: 请输入有效的HTTP/HTTPS链接")
            input("按回车键返回主菜单...")
            return
        
        # 执行转换
        success = self.process_m3u8_url(m3u8_url)
        
        # 清理临时文件
        self.clear_temp()
        
        # 显示选项
        print("\n" + "-"*50)
        if success:
            print("✓ 转换已完成!")
        print("1. 返回主菜单")
        print("2. 退出")
        
        while True:
            choice = input("请选择 (1-2): ").strip()
            if choice == '1':
                return
            elif choice == '2':
                print("\n感谢使用，再见！")
                sys.exit(0)
            else:
                print("错误 455: 无效的选择，请重新输入")
    
    def local_conversion(self):
        """本地文件转换流程"""
        print("\n" + "-"*50)
        print("本地 m3u8 文件转换")
        print("-"*50)
        print("提示: 请确保m3u8文件中的TS片段路径正确")
        print("      可以是绝对路径、相对路径或网络链接")
        print("-"*50)
        
        file_path = input("请输入本地 m3u8 文件路径: ").strip()
        
        if not file_path:
            print("\n错误 455: 路径不能为空")
            input("按回车键返回主菜单...")
            return
        
        # 移除可能存在的引号
        file_path = file_path.strip('"\'')
        
        # 执行转换
        success = self.process_local_m3u8(file_path)
        
        # 清理临时文件
        self.clear_temp()
        
        # 显示选项
        print("\n" + "-"*50)
        if success:
            print("✓ 转换已完成!")
        print("1. 返回主菜单")
        print("2. 退出")
        
        while True:
            choice = input("请选择 (1-2): ").strip()
            if choice == '1':
                return
            elif choice == '2':
                print("\n感谢使用，再见！")
                sys.exit(0)
            else:
                print("错误 455: 无效的选择，请重新输入")

def check_dependencies():
    """检查必要的依赖库"""
    try:
        import requests
        import m3u8
    except ImportError as e:
        print("错误: 缺少必要的依赖库!")
        print("\n请安装以下依赖:")
        print("pip install requests")
        print("pip install m3u8")
        return False
    return True

if __name__ == "__main__":
    # 检查依赖
    if not check_dependencies():
        input("\n按回车键退出...")
        sys.exit(1)
    
    # 创建转换器实例并运行
    converter = M3U8Converter()
    
    try:
        converter.main_menu()
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
        converter.clear_temp()
        sys.exit(0)
    except Exception as e:
        print(f"\n程序运行出错: {e}")
        converter.clear_temp()
        input("按回车键退出...")