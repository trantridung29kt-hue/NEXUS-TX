from flask import Flask, render_template_string, jsonify, request
import requests
import json
import threading
import time
from collections import deque, defaultdict
import logging
import math
from datetime import datetime
import sys
import os
from typing import Dict, List, Tuple, Optional, Any
import urllib3

# Tắt cảnh báo SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ======= CẤU HÌNH GAME =======
# Token từ request của bạn
BEARER_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjb2RlIjowLCJtZXNzYWdlIjoiU3VjY2VzcyIsIm5pY2tOYW1lIjoic2pnZXIzNTMiLCJhY2Nlc3NUb2tlbiI6ImI0MjNkZGIxMTRjNzhhMWM0ZGJhZTQ5NDczMzY0ZGVkIiwiaXNMb2dpbiI6dHJ1ZSwibW9uZXkiOjAsImlkIjoiODY1NjM1OCIsInVzZXJuYW1lIjoia2llbnBoYW0wNjExIiwiaWF0IjoxNzgyNjY4OTI3LCJleHAiOjE3ODI2OTc3Mjd9.Zh26HDILRXHIXUN5pAn0GZj92xvnKraY2XkMKLTGXWs"

# Headers mặc định cho tất cả request
DEFAULT_HEADERS = {
    'accept': '*/*',
    'accept-language': 'en-US,en;q=0.9,vi;q=0.8',
    'authorization': f'Bearer {BEARER_TOKEN}',
    'content-type': 'application/json',
    'origin': 'https://lc79b.bet',
    'priority': 'u=1, i',
    'referer': 'https://lc79b.bet/',
    'sec-ch-ua': '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"iOS"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'cross-site',
    'user-agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1',
}

GAME_CONFIG = {
    'lc79': {
        'name': 'LC79',
        'color': '#ff6b35',
        'md5_url': 'https://wtxmd52.tele68.com/v1/txmd5/sessions',
        'hu_url': 'https://wtx.tele68.com/v1/tx/sessions',
        'bet_url': 'https://lc79.bet',
        'active': True,
        'params': {
            'cp': 'R',
            'cl': 'R',
            'pf': 'web',
            'at': 'b423ddb114c78a1c4dbae49473364ded'
        },
        'headers': DEFAULT_HEADERS.copy()
    },
    'betvip': {
        'name': 'BETVIP',
        'color': '#8b6cff',
        'md5_url': 'https://wtxmd52.macminim6.online/v1/txmd5/sessions',
        'hu_url': 'https://wtx.macminim6.online/v1/tx/sessions',
        'bet_url': 'https://betvip.com',
        'active': False,
        'params': {
            'cp': 'R',
            'cl': 'R',
            'pf': 'web',
            'at': 'f5252fdaf1287cdbfdc6de625acf5611'
        },
        'headers': {}
    }
}

current_game = 'lc79'

# ======= DICE HISTORY RETRIEVAL ENGINE =======

class DiceHistoryEngine:
    def __init__(self):
        self.history = []
        self.index_by_dice = defaultdict(list)
        self.index_by_sum = defaultdict(list)
        self.index_by_type = defaultdict(list)
        self.last_update = None
        self.total_samples = 0
        self.session_ids = set()
        
    def get_dice_key(self, dices: List[int]) -> str:
        if not dices:
            return ""
        return "-".join(str(d) for d in sorted(dices))
    
    def get_dice_sum(self, dices: List[int]) -> int:
        return sum(dices) if dices else 0
    
    def get_dice_type(self, dices: List[int]) -> str:
        if not dices:
            return "unknown"
        unique = set(dices)
        if len(unique) == 1:
            return "triple"
        elif len(unique) == 2:
            return "pair"
        else:
            return "mixed"
    
    def get_parity_pattern(self, dices: List[int]) -> str:
        if not dices:
            return ""
        return "".join("E" if d % 2 == 0 else "O" for d in sorted(dices))
    
    def get_high_low_pattern(self, dices: List[int]) -> str:
        if not dices:
            return ""
        return "".join("H" if d >= 4 else "L" for d in sorted(dices))
    
    def build_index(self, sessions: List[Dict]):
        self.history = sessions
        self.index_by_dice.clear()
        self.index_by_sum.clear()
        self.index_by_type.clear()
        self.session_ids.clear()
        
        for session in sessions:
            session_id = session.get('id')
            if session_id:
                self.session_ids.add(session_id)
            
            dices = session.get('dices', [])
            if not dices:
                continue
                
            dice_key = self.get_dice_key(dices)
            dice_sum = self.get_dice_sum(dices)
            dice_type = self.get_dice_type(dices)
            
            self.index_by_dice[dice_key].append(session)
            self.index_by_sum[dice_sum].append(session)
            self.index_by_type[dice_type].append(session)
        
        self.total_samples = len(sessions)
        self.last_update = datetime.now()
        logging.info(f"📊 Đã xây dựng index: {len(sessions)} phiên, {len(self.index_by_dice)} bộ xúc xắc khác nhau")
    
    def calculate_similarity_score(self, target_dices: List[int], matched_dices: List[int]) -> float:
        if not target_dices or not matched_dices:
            return 0.0
            
        target_sorted = sorted(target_dices)
        matched_sorted = sorted(matched_dices)
        
        if target_sorted == matched_sorted:
            return 1.0
        
        if (sum(target_dices) == sum(matched_dices) and 
            self.get_dice_type(target_dices) == self.get_dice_type(matched_dices)):
            return 0.9
        
        common = set(target_sorted) & set(matched_sorted)
        if len(common) >= 2:
            return 0.8
        
        if sum(target_dices) == sum(matched_dices):
            return 0.7
        
        if self.get_dice_type(target_dices) == self.get_dice_type(matched_dices):
            return 0.6
        
        if self.get_parity_pattern(target_dices) == self.get_parity_pattern(matched_dices):
            return 0.5
        
        if self.get_high_low_pattern(target_dices) == self.get_high_low_pattern(matched_dices):
            return 0.4
            
        return 0.0
    
    def find_matches(self, target_session: Dict) -> Dict:
        target_dices = target_session.get('dices', [])
        if not target_dices:
            return {'exact_matches': [], 'similar_matches': [], 'all_matches': []}
        
        target_key = self.get_dice_key(target_dices)
        target_sum = self.get_dice_sum(target_dices)
        target_type = self.get_dice_type(target_dices)
        target_id = target_session.get('id')
        
        exact_matches = []
        similar_matches = []
        all_matches = []
        seen_ids = set()
        
        exact = self.index_by_dice.get(target_key, [])
        for session in exact:
            session_id = session.get('id')
            if session_id and session_id != target_id:
                if session_id not in seen_ids:
                    seen_ids.add(session_id)
                    exact_matches.append(session)
                    all_matches.append(session)
        
        for session in self.index_by_sum.get(target_sum, []):
            session_id = session.get('id')
            if session_id and session_id != target_id and session_id not in seen_ids:
                if self.get_dice_type(session.get('dices', [])) == target_type:
                    seen_ids.add(session_id)
                    similar_matches.append(session)
                    all_matches.append(session)
        
        for session in self.index_by_sum.get(target_sum, []):
            session_id = session.get('id')
            if session_id and session_id != target_id and session_id not in seen_ids:
                seen_ids.add(session_id)
                similar_matches.append(session)
                all_matches.append(session)
        
        for session in self.index_by_type.get(target_type, []):
            session_id = session.get('id')
            if session_id and session_id != target_id and session_id not in seen_ids:
                seen_ids.add(session_id)
                similar_matches.append(session)
                all_matches.append(session)
        
        for session in self.history:
            session_id = session.get('id')
            if not session_id or session_id == target_id or session_id in seen_ids:
                continue
            
            session_dices = session.get('dices', [])
            similarity = self.calculate_similarity_score(target_dices, session_dices)
            if similarity >= 0.5:
                seen_ids.add(session_id)
                similar_matches.append(session)
                all_matches.append(session)
        
        return {
            'exact_matches': exact_matches,
            'similar_matches': similar_matches,
            'all_matches': all_matches
        }
    
    def get_next_session(self, session: Dict) -> Optional[Dict]:
        current_id = session.get('id')
        if not current_id:
            return None
        
        for i, s in enumerate(self.history):
            if s.get('id') == current_id and i > 0:
                return self.history[i-1]
        return None
    
    def calculate_average_similarity(self, target_dices: List[int], matches: List[Dict]) -> float:
        if not matches:
            return 0.0
        
        total = 0.0
        for match in matches:
            match_dices = match.get('dices', [])
            similarity = self.calculate_similarity_score(target_dices, match_dices)
            total += similarity
        
        return total / len(matches)
    
    def calculate_stability(self, matches: List[Dict]) -> float:
        if len(matches) < 3:
            return 0.0
        
        results = []
        for match in matches:
            next_session = self.get_next_session(match)
            if next_session:
                results.append(next_session.get('resultTruyenThong', ''))
        
        if not results:
            return 0.0
        
        tai_count = results.count('TAI')
        xiu_count = results.count('XIU')
        total = len(results)
        
        if total == 0:
            return 0.0
        
        return max(tai_count, xiu_count) / total
    
    def analyze(self, target_session: Dict, min_samples: int = 5) -> Dict:
        target_dices = target_session.get('dices', [])
        if not target_dices:
            return self.get_empty_result(target_session)
        
        matches = self.find_matches(target_session)
        exact_matches = matches['exact_matches']
        similar_matches = matches['similar_matches']
        all_matches = matches['all_matches']
        
        if len(all_matches) < min_samples:
            return {
                'prediction': 'NO SIGNAL',
                'probability': 0.0,
                'confidence': 0.0,
                'samples': len(all_matches),
                'exact_samples': len(exact_matches),
                'similar_samples': len(similar_matches),
                'history_size': self.total_samples,
                'similarity_score': 0.0,
                'last_dice': target_dices,
                'signal': 'NO_SIGNAL'
            }
        
        tai_count = 0
        xiu_count = 0
        weighted_tai = 0.0
        weighted_xiu = 0.0
        total_weight = 0.0
        
        for session in exact_matches:
            next_session = self.get_next_session(session)
            if next_session:
                next_result = next_session.get('resultTruyenThong', '')
                if next_result == 'TAI':
                    tai_count += 1
                    weighted_tai += 1.0
                elif next_result == 'XIU':
                    xiu_count += 1
                    weighted_xiu += 1.0
                total_weight += 1.0
        
        for session in similar_matches:
            session_id = session.get('id')
            is_in_exact = any(s.get('id') == session_id for s in exact_matches)
            if is_in_exact:
                continue
                
            next_session = self.get_next_session(session)
            if next_session:
                next_result = next_session.get('resultTruyenThong', '')
                similarity = self.calculate_similarity_score(target_dices, session.get('dices', []))
                
                if next_result == 'TAI':
                    tai_count += 1
                    weighted_tai += similarity
                elif next_result == 'XIU':
                    xiu_count += 1
                    weighted_xiu += similarity
                total_weight += similarity
        
        total_samples = tai_count + xiu_count
        
        if total_samples < min_samples or total_weight == 0:
            return {
                'prediction': 'NO SIGNAL',
                'probability': 0.0,
                'confidence': 0.0,
                'samples': total_samples,
                'exact_samples': len(exact_matches),
                'similar_samples': len(similar_matches),
                'history_size': self.total_samples,
                'similarity_score': 0.0,
                'last_dice': target_dices,
                'signal': 'NO_SIGNAL'
            }
        
        prob_tai = weighted_tai / total_weight if total_weight > 0 else 0.0
        prob_xiu = weighted_xiu / total_weight if total_weight > 0 else 0.0
        
        sample_ratio = min(1.0, total_samples / 50)
        similarity_avg = self.calculate_average_similarity(target_dices, all_matches)
        stability = self.calculate_stability(all_matches)
        
        confidence = (sample_ratio * 0.4 + similarity_avg * 0.3 + stability * 0.3) * 100
        
        if stability < 0.6:
            confidence *= 0.8
        
        exact_ratio = len(exact_matches) / max(1, total_samples)
        if exact_ratio > 0.3:
            confidence = min(100, confidence * 1.1)
        
        confidence = min(100, max(0, confidence))
        
        if prob_tai > 0.52 and confidence > 60:
            prediction = 'TAI'
        elif prob_xiu > 0.52 and confidence > 60:
            prediction = 'XIU'
        else:
            prediction = 'CÂN NHẮC' if confidence > 50 else 'NO SIGNAL'
        
        return {
            'prediction': prediction,
            'probability': max(prob_tai, prob_xiu) * 100,
            'confidence': round(confidence, 1),
            'samples': total_samples,
            'exact_samples': len(exact_matches),
            'similar_samples': len(similar_matches),
            'history_size': self.total_samples,
            'similarity_score': round(similarity_avg * 100, 1),
            'last_dice': target_dices,
            'prob_tai': round(prob_tai * 100, 1),
            'prob_xiu': round(prob_xiu * 100, 1),
            'tai_count': tai_count,
            'xiu_count': xiu_count,
            'signal': prediction if prediction != 'NO SIGNAL' else 'NO_SIGNAL'
        }
    
    def get_empty_result(self, target_session: Dict) -> Dict:
        return {
            'prediction': 'NO SIGNAL',
            'probability': 0.0,
            'confidence': 0.0,
            'samples': 0,
            'exact_samples': 0,
            'similar_samples': 0,
            'history_size': self.total_samples,
            'similarity_score': 0.0,
            'last_dice': target_session.get('dices', []),
            'signal': 'NO_SIGNAL'
        }

# ======= CẤU TRÚC DỮ LIỆU =======
def tao_cau_truc_loai():
    return {
        "toan_bo_lich_su": [],
        "van_gan_nhat": None,
        "du_doan_van_tiep": None,
        "lich_su_dung_sai": deque(maxlen=500),
        "lan_cap_nhat_truoc": None,
        "thoi_gian_cap_nhat": None,
        "thong_ke_tong_hop": {
            "tong_du_doan": 0,
            "tong_dung": 0,
            "tong_sai": 0,
            "ty_le_thang": 0
        }
    }

du_lieu = {}
engines = {}

def khoi_tao_du_lieu():
    global du_lieu, engines
    du_lieu = {
        "hu": tao_cau_truc_loai(),
        "md5": tao_cau_truc_loai()
    }
    engines = {
        "hu": DiceHistoryEngine(),
        "md5": DiceHistoryEngine()
    }
    logging.info("✅ Đã khởi tạo dữ liệu")

khoi_tao_du_lieu()

# ======= LẤY DỮ LIỆU =======
def lay_toan_bo_lich_su(url):
    """Lấy dữ liệu từ API với headers và params đầy đủ"""
    config = GAME_CONFIG[current_game]
    
    # Lấy headers từ config
    headers = config.get('headers', DEFAULT_HEADERS.copy())
    
    # Lấy params từ config
    params = config.get('params', {})
    
    logging.info(f"🔑 Đang gọi API: {url}")
    
    for attempt in range(3):
        try:
            # Gọi API với params và headers
            response = requests.get(
                url, 
                params=params, 
                headers=headers, 
                timeout=30, 
                verify=False
            )
            
            logging.info(f"Status: {response.status_code}")
            logging.info(f"Response length: {len(response.text)}")
            
            if response.status_code == 200:
                if response.text and response.text.strip():
                    try:
                        data = response.json()
                        if 'list' in data and len(data['list']) > 0:
                            logging.info(f"✅ Thành công: {len(data['list'])} phiên")
                            if len(data['list']) > 0:
                                sample = data['list'][0]
                                logging.info(f"📝 Sample: {sample.get('dices', [])} - {sample.get('resultTruyenThong', '')}")
                            return data['list']
                        else:
                            logging.warning(f"⚠️ Danh sách rỗng hoặc không có key 'list'")
                    except json.JSONDecodeError as e:
                        logging.warning(f"⚠️ JSON decode error: {e}")
                        logging.warning(f"Response: {response.text[:200]}")
                else:
                    logging.warning(f"⚠️ Response rỗng")
            elif response.status_code == 403:
                logging.error(f"❌ Lỗi 403 - Token hết hạn!")
                break
            elif response.status_code == 429:
                logging.warning(f"⚠️ Rate limit, chờ 10s...")
                time.sleep(10)
            else:
                logging.warning(f"⚠️ Status code: {response.status_code}")
                
        except requests.exceptions.Timeout:
            logging.warning(f"Attempt {attempt+1}/3: Timeout")
            time.sleep(3)
        except requests.exceptions.RequestException as e:
            logging.warning(f"Attempt {attempt+1}/3: {str(e)[:100]}")
            time.sleep(3)
        except Exception as e:
            logging.error(f"Lỗi: {e}")
            time.sleep(3)
    
    # Nếu thất bại, dùng dữ liệu mẫu
    logging.warning("⚠️ Sử dụng dữ liệu mẫu")
    return tao_du_lieu_mau()

def tao_du_lieu_mau():
    """Tạo dữ liệu mẫu để test"""
    import random
    sample_data = []
    results = ['TAI', 'XIU']
    for i in range(50):
        dices = [random.randint(1, 6) for _ in range(3)]
        point = sum(dices)
        result = 'TAI' if point >= 11 else 'XIU'
        sample_data.append({
            'id': i + 1,
            'dices': dices,
            'point': point,
            'resultTruyenThong': result
        })
    return sample_data

# ======= PHÂN TÍCH =======
def phan_tich_voi_engine(danh_sach, loai):
    if not danh_sach or len(danh_sach) < 5:
        logging.warning(f"⚠️ {loai}: Không đủ dữ liệu ({len(danh_sach) if danh_sach else 0})")
        return tao_du_doan_mac_dinh(danh_sach, loai)
    
    engine = engines.get(loai)
    if not engine:
        logging.warning(f"⚠️ {loai}: Engine không tồn tại")
        return tao_du_doan_mac_dinh(danh_sach, loai)
    
    if engine.total_samples != len(danh_sach):
        engine.build_index(danh_sach)
    
    van_hien_tai = danh_sach[0]
    result = engine.analyze(van_hien_tai)
    
    logging.info(f"📊 {loai} - Prediction: {result['prediction']}, Confidence: {result['confidence']}%")
    
    return {
        'khuyen_nghi': result['prediction'],
        'xac_suat_tai': result.get('prob_tai', 0) / 100,
        'xac_suat_xiu': result.get('prob_xiu', 0) / 100,
        'do_tin_cay': 'Cao' if result['confidence'] > 75 else 'Trung bình' if result['confidence'] > 50 else 'Thấp',
        'do_tin_cay_so': result['confidence'],
        'van_gan_nhat': van_hien_tai,
        'ket_qua_hien_tai': van_hien_tai.get('resultTruyenThong', ''),
        'tong_so_van': result['history_size'],
        'so_tai': result.get('tai_count', 0),
        'so_xiu': result.get('xiu_count', 0),
        'chieu_dai_chuoi': 0,
        'exact_samples': result['exact_samples'],
        'similar_samples': result['similar_samples'],
        'similarity_score': result['similarity_score'],
        'samples': result['samples'],
        'last_dice': result.get('last_dice', []),
        'signal': result.get('signal', 'NO_SIGNAL')
    }

def tao_du_doan_mac_dinh(danh_sach, loai=""):
    van_gan = danh_sach[0] if danh_sach else None
    return {
        'khuyen_nghi': 'CHUA_DU_DU_LIEU',
        'xac_suat_tai': 0.5,
        'xac_suat_xiu': 0.5,
        'do_tin_cay': 'Thap',
        'do_tin_cay_so': 0,
        'van_gan_nhat': van_gan,
        'ket_qua_hien_tai': van_gan.get('resultTruyenThong') if van_gan else None,
        'tong_so_van': len(danh_sach) if danh_sach else 0,
        'so_tai': 0,
        'so_xiu': 0,
        'chieu_dai_chuoi': 0,
        'exact_samples': 0,
        'similar_samples': 0,
        'similarity_score': 0,
        'samples': 0,
        'last_dice': [],
        'signal': 'NO_SIGNAL'
    }

# ======= HÀM ĐỊNH DẠNG =======
def dinh_dang_xuc_xac(van):
    if not van:
        return ''
    xx = van.get('dices')
    if isinstance(xx, (list, tuple)) and len(xx) > 0:
        return '-'.join(str(x) for x in xx)
    return str(van.get('point', ''))

# ======= CẬP NHẬT DỮ LIỆU =======
def cap_nhat_loai(loai, url):
    """Cập nhật dữ liệu cho loại (hu hoặc md5)"""
    data = du_lieu[loai]
    engine = engines[loai]
    
    logging.info(f"🔄 Bắt đầu cập nhật {loai}")
    
    while True:
        try:
            # Lấy dữ liệu từ API
            danh_sach = lay_toan_bo_lich_su(url)
            
            if not danh_sach:
                logging.warning(f"⚠️ {loai}: Không có dữ liệu, chờ 5s...")
                time.sleep(5)
                continue
            
            # Cập nhật lịch sử
            data['toan_bo_lich_su'] = danh_sach
            van_gan = danh_sach[0]
            van_id = van_gan.get('id')
            
            # Xây dựng index
            engine.build_index(danh_sach)
            
            # Kiểm tra xem đã có phiên mới chưa
            if data['lan_cap_nhat_truoc'] is None or data['lan_cap_nhat_truoc'] != van_id:
                logging.info(f"🔄 {loai}: Phiên mới {van_id}")
                
                # Đánh giá dự đoán cũ
                if data['du_doan_van_tiep'] and data['van_gan_nhat']:
                    du_doan_cu = data['du_doan_van_tiep'].get('khuyen_nghi')
                    ket_qua_thuc = van_gan.get('resultTruyenThong')
                    
                    if du_doan_cu in ['TAI', 'XIU'] and ket_qua_thuc:
                        dung = (du_doan_cu == ket_qua_thuc)
                        data['lich_su_dung_sai'].append({
                            'du_doan': du_doan_cu,
                            'ket_qua': ket_qua_thuc,
                            'dung': dung,
                            'diem': van_gan.get('point'),
                            'xuc_xac': dinh_dang_xuc_xac(van_gan),
                            'thoi_gian': datetime.now().strftime('%H:%M:%S')
                        })
                        
                        data['thong_ke_tong_hop']['tong_du_doan'] += 1
                        if dung:
                            data['thong_ke_tong_hop']['tong_dung'] += 1
                        else:
                            data['thong_ke_tong_hop']['tong_sai'] += 1
                        
                        tong = data['thong_ke_tong_hop']['tong_du_doan']
                        if tong > 0:
                            data['thong_ke_tong_hop']['ty_le_thang'] = round(
                                data['thong_ke_tong_hop']['tong_dung'] / tong * 100, 1
                            )
                
                # Phân tích mới
                du_doan_moi = phan_tich_voi_engine(danh_sach, loai)
                data['van_gan_nhat'] = van_gan
                data['du_doan_van_tiep'] = du_doan_moi
                data['lan_cap_nhat_truoc'] = van_id
                data['thoi_gian_cap_nhat'] = datetime.now().strftime('%H:%M:%S')
                
                logging.info(f"✅ {loai}: Đã cập nhật - {len(danh_sach)} phiên, Dự đoán: {du_doan_moi.get('khuyen_nghi', 'N/A')}")
                
        except Exception as e:
            logging.error(f"❌ Lỗi cập nhật {loai}: {e}")
            import traceback
            logging.error(traceback.format_exc())
        
        time.sleep(5)

def start_updater(game_key):
    global current_game
    current_game = game_key
    config = GAME_CONFIG[game_key]
    
    khoi_tao_du_lieu()
    
    # Khởi động threads
    thread_hu = threading.Thread(target=cap_nhat_loai, args=('hu', config['hu_url']), daemon=True)
    thread_md5 = threading.Thread(target=cap_nhat_loai, args=('md5', config['md5_url']), daemon=True)
    
    thread_hu.start()
    thread_md5.start()
    
    logging.info(f"🔄 Đã chuyển sang game: {config['name']}")

# Khởi động với LC79
start_updater('lc79')

# ======= ROUTES =======
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, 
                                 du_lieu=du_lieu, 
                                 game_config=GAME_CONFIG,
                                 current_game=current_game)

@app.route('/api/du_lieu/<loai>')
def api_du_lieu(loai):
    return jsonify(du_lieu.get(loai, {}).get('du_doan_van_tiep'))

@app.route('/api/all')
def api_all():
    result = {}
    for loai in ['hu', 'md5']:
        data = du_lieu[loai]
        result[loai] = {
            'du_doan_van_tiep': data['du_doan_van_tiep'],
            'van_gan_nhat': data['van_gan_nhat'],
            'thong_ke_tong_hop': data['thong_ke_tong_hop'],
            'thoi_gian_cap_nhat': data['thoi_gian_cap_nhat'],
            'lich_su_dung_sai': list(data['lich_su_dung_sai'])[-30:] if data['lich_su_dung_sai'] else []
        }
    return jsonify(result)

@app.route('/api/switch_game', methods=['POST'])
def switch_game():
    data = request.get_json()
    game_key = data.get('game')
    
    if game_key not in GAME_CONFIG:
        return jsonify({'error': 'Game không tồn tại'}), 400
    
    if not GAME_CONFIG[game_key]['active']:
        return jsonify({'error': 'Game đang bảo trì'}), 400
    
    start_updater(game_key)
    
    return jsonify({
        'success': True,
        'game': game_key,
        'message': f'Đã chuyển sang {GAME_CONFIG[game_key]["name"]}'
    })


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>NEXUS · Tài Xỉu Dice History</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{
  --bg-0:#05060a; --bg-1:#0a0d16; --bg-2:#0e1320;
  --glass:rgba(255,255,255,.04); --glass-2:rgba(255,255,255,.07);
  --border:rgba(255,255,255,.08); --border-strong:rgba(255,255,255,.16);
  --text:#e8eaf0; --text-dim:#8b91a3; --text-faint:#525a6e;
  --blue:#3b9eff; --blue-soft:rgba(59,158,255,.16);
  --rose:#ff4d6d; --rose-soft:rgba(255,77,109,.16);
  --purple:#8b6cff; --cyan:#00d9c0; --emerald:#2bd97c; --amber:#ffb454;
  --orange:#ff8c42; --orange-soft:rgba(255,140,66,.16);
  --radius-lg:24px; --radius-md:16px; --radius-sm:10px;
}
*{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  font-family:'Inter',sans-serif; color:var(--text);
  background:var(--bg-0); min-height:100vh; overflow-x:hidden;
  -webkit-font-smoothing:antialiased;
}
.mono{font-family:'JetBrains Mono',monospace}
.display{font-family:'Space Grotesk',sans-serif}

.mesh{
  position:fixed; inset:0; z-index:0; pointer-events:none;
  background:
    radial-gradient(ellipse 900px 700px at 12% -8%, rgba(59,158,255,.18), transparent 60%),
    radial-gradient(ellipse 800px 800px at 105% 8%, rgba(139,108,255,.16), transparent 60%),
    radial-gradient(ellipse 700px 600px at 50% 105%, rgba(255,77,109,.10), transparent 60%),
    radial-gradient(ellipse 600px 600px at -5% 90%, rgba(255,140,66,.10), transparent 60%),
    linear-gradient(180deg, var(--bg-0), var(--bg-1) 40%, var(--bg-0));
  animation:meshDrift 22s ease-in-out infinite alternate;
}
@keyframes meshDrift{
  0%{filter:hue-rotate(0deg) brightness(1)}
  100%{filter:hue-rotate(8deg) brightness(1.06)}
}
.grain{
  position:fixed; inset:0; z-index:1; pointer-events:none; opacity:.025; mix-blend-mode:overlay;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='80' height='80'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
}

.shell{position:relative; z-index:2; max-width:1400px; margin:0 auto; padding:22px 20px 80px}

.header{
  display:flex; align-items:center; justify-content:space-between; gap:18px;
  flex-wrap:wrap; padding:16px 22px; margin-bottom:22px;
  background:var(--glass); border:1px solid var(--border); border-radius:var(--radius-lg);
  backdrop-filter:blur(20px); -webkit-backdrop-filter:blur(20px);
  animation:fadeSlideDown .6s ease both;
}
@keyframes fadeSlideDown{from{opacity:0; transform:translateY(-14px)} to{opacity:1; transform:translateY(0)}}
.brand{display:flex; align-items:center; gap:13px}
.brand-mark{
  width:42px; height:42px; border-radius:13px; position:relative; flex:none;
  background:linear-gradient(135deg, var(--blue), var(--purple));
  box-shadow:0 0 22px rgba(59,158,255,.45), inset 0 0 0 1px rgba(255,255,255,.2);
  display:flex; align-items:center; justify-content:center;
}
.brand-mark svg{width:22px; height:22px}
.brand-text .name{font-family:'Space Grotesk',sans-serif; font-weight:700; font-size:1.12em; letter-spacing:.3px}
.brand-text .tag{font-size:.7em; color:var(--text-dim); margin-top:1px; letter-spacing:.4px}

.hud{display:flex; align-items:center; gap:22px; flex-wrap:wrap}
.hud-item{display:flex; flex-direction:column; align-items:flex-end; gap:2px}
.hud-label{font-size:.62em; color:var(--text-faint); text-transform:uppercase; letter-spacing:1px}
.hud-value{font-size:.84em; font-weight:600; color:var(--text)}

.game-selector {
  display:flex; align-items:center; gap:10px;
  background:var(--glass-2); border:1px solid var(--border);
  border-radius:var(--radius-sm); padding:4px;
}
.game-btn {
  padding:6px 16px; border-radius:8px; border:none;
  background:transparent; color:var(--text-dim);
  font-family:'Inter',sans-serif; font-weight:600; font-size:.8em;
  cursor:pointer; transition:all .25s;
}
.game-btn:hover {
  color:var(--text); background:rgba(255,255,255,.05);
}
.game-btn.active {
  color:#fff; background:var(--accent, var(--purple));
  box-shadow:0 0 20px rgba(139,108,255,.3);
}
.game-btn.lc79.active { --accent:#ff6b35; }
.game-btn.betvip.active { --accent:#8b6cff; }

.bet-btn{
  display:inline-flex; align-items:center; gap:8px;
  padding:8px 20px; border-radius:99px;
  background:linear-gradient(135deg, #ff6b35, #ff4500);
  color:#fff; font-weight:700; font-size:.85em;
  text-decoration:none; border:none; cursor:pointer;
  box-shadow:0 0 25px rgba(255,69,0,.35);
  transition:transform .25s, box-shadow .25s;
}
.bet-btn:hover{transform:scale(1.04); box-shadow:0 0 35px rgba(255,69,0,.5);}
.live-chip{
  display:flex; align-items:center; gap:7px; padding:6px 12px 6px 10px;
  background:rgba(43,217,124,.1); border:1px solid rgba(43,217,124,.3); border-radius:99px;
}
.live-dot{width:7px; height:7px; border-radius:50%; background:var(--emerald); box-shadow:0 0 8px var(--emerald);
  animation:pulseDot 1.6s ease-in-out infinite}
@keyframes pulseDot{0%,100%{opacity:1; transform:scale(1)} 50%{opacity:.5; transform:scale(.78)}}
.live-text{font-size:.72em; font-weight:600; color:var(--emerald); letter-spacing:.5px}

.gcard{
  position:relative; background:var(--glass); border:1px solid var(--border);
  border-radius:var(--radius-lg); backdrop-filter:blur(18px); -webkit-backdrop-filter:blur(18px);
  overflow:hidden; transition:border-color .35s, transform .35s, box-shadow .35s;
}
.gcard::before{
  content:''; position:absolute; inset:0; border-radius:inherit; padding:1px;
  background:linear-gradient(135deg, rgba(59,158,255,.35), rgba(139,108,255,.12) 40%, transparent 70%);
  -webkit-mask:linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite:xor; mask-composite:exclude; pointer-events:none; opacity:.7;
}
.gcard:hover{border-color:var(--border-strong); transform:translateY(-2px); box-shadow:0 16px 40px rgba(0,0,0,.35)}
.gcard-head{display:flex; align-items:center; justify-content:space-between; padding:18px 22px; position:relative; z-index:1}
.eyebrow{font-size:.68em; font-weight:700; color:var(--text-dim); text-transform:uppercase; letter-spacing:1.6px; display:flex; align-items:center; gap:8px}

.dual-grid{display:grid; grid-template-columns:1fr 1fr; gap:18px; margin-bottom:18px}
@media(max-width:860px){.dual-grid{grid-template-columns:1fr}}

#hu-container .gcard { border-color:rgba(255,140,66,.3); }
#hu-container .eyebrow:first-child { color:var(--orange); }

#md5-container .gcard { border-color:rgba(59,158,255,.3); }
#md5-container .eyebrow:first-child { color:var(--blue); }

.hero{padding:8px 22px 26px; position:relative; z-index:1}
.hero-top{display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; color:var(--text-dim); font-size:.82em; margin-bottom:6px}
.hero-top b{color:var(--text); font-weight:600}
.dice-chip{display:flex; gap:5px}
.die{
  width:26px; height:26px; border-radius:7px; background:var(--glass-2); border:1px solid var(--border);
  display:flex; align-items:center; justify-content:center; font-size:.78em; font-weight:700;
}

.hero-main{display:flex; align-items:center; justify-content:center; gap:36px; flex-wrap:wrap; padding:18px 0 6px}
.gauge-wrap{position:relative; width:200px; height:200px; flex:none}
.gauge-wrap svg{width:100%; height:100%; transform:rotate(-90deg)}
.gauge-track{fill:none; stroke:rgba(255,255,255,.06); stroke-width:14}
.gauge-fill{fill:none; stroke-width:14; stroke-linecap:round; transition:stroke-dashoffset 1s cubic-bezier(.22,1,.36,1), stroke .5s}
.gauge-center{position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:2px}
.gauge-call{font-family:'Space Grotesk',sans-serif; font-weight:700; font-size:1.8em; letter-spacing:-.5px; transition:color .4s}
.gauge-sub{font-size:.6em; color:var(--text-faint); text-transform:uppercase; letter-spacing:1.5px}
.gauge-conf{font-size:.7em; font-weight:600; color:var(--amber); margin-top:2px}

.prob-cols{display:flex; flex-direction:column; gap:12px; min-width:180px}
.prob-row{display:flex; flex-direction:column; gap:5px}
.prob-row-top{display:flex; justify-content:space-between; align-items:baseline}
.prob-name{font-size:.75em; font-weight:600; color:var(--text-dim); letter-spacing:.3px}
.prob-pct{font-family:'JetBrains Mono',monospace; font-weight:700; font-size:1em}
.prob-track{height:5px; border-radius:4px; background:rgba(255,255,255,.06); overflow:hidden}
.prob-fill{height:100%; border-radius:4px; transition:width 1s cubic-bezier(.22,1,.36,1)}

.metric-strip{display:grid; grid-template-columns:repeat(4,1fr); gap:1px; margin-top:20px; background:var(--border); border-radius:var(--radius-md); overflow:hidden}
.metric-cell{background:rgba(10,13,22,.6); padding:12px 8px; text-align:center}
.metric-num{font-family:'JetBrains Mono',monospace; font-weight:700; font-size:1em; color:var(--text)}
.metric-lbl{font-size:.58em; color:var(--text-faint); text-transform:uppercase; letter-spacing:.6px; margin-top:3px}

.engine-stats{display:grid; grid-template-columns:repeat(4,1fr); gap:10px; padding:16px 22px 20px}
@media(max-width:600px){.engine-stats{grid-template-columns:1fr 1fr}}
.engine-stat{
  background:var(--glass-2); border:1px solid var(--border); border-radius:var(--radius-sm);
  padding:14px; display:flex; flex-direction:column; gap:3px;
}
.engine-stat .v{font-family:'JetBrains Mono',monospace; font-weight:700; font-size:1.2em}
.engine-stat .l{font-size:.62em; color:var(--text-faint); text-transform:uppercase; letter-spacing:.6px}

.stats-grid{display:grid; grid-template-columns:repeat(4,1fr); gap:10px; padding:16px 22px 20px}
@media(max-width:600px){.stats-grid{grid-template-columns:1fr 1fr}}
.stat-box{
  background:var(--glass-2); border:1px solid var(--border); border-radius:var(--radius-sm);
  padding:14px; display:flex; flex-direction:column; gap:3px;
}
.stat-box .v{font-family:'JetBrains Mono',monospace; font-weight:700; font-size:1.2em}
.stat-box .l{font-size:.62em; color:var(--text-faint); text-transform:uppercase; letter-spacing:.6px}

.timeline{padding:6px 14px 16px; max-height:400px; overflow-y:auto}
.timeline::-webkit-scrollbar{width:6px}
.timeline::-webkit-scrollbar-thumb{background:var(--border-strong); border-radius:3px}
.t-row{
  display:grid; grid-template-columns:auto 1fr auto; gap:12px; align-items:center;
  padding:10px 8px; border-radius:var(--radius-sm); transition:background .25s;
  animation:rowIn .4s ease both;
}
@keyframes rowIn{from{opacity:0; transform:translateX(-6px)} to{opacity:1; transform:translateX(0)}}
.t-row:hover{background:rgba(255,255,255,.04)}
.t-rail{display:flex; flex-direction:column; align-items:center; gap:0; position:relative; width:12px}
.t-dot{width:8px; height:8px; border-radius:50%; flex:none; z-index:1; box-shadow:0 0 8px currentColor}
.t-line{position:absolute; top:8px; bottom:-18px; width:1px; background:var(--border)}
.t-row:last-child .t-line{display:none}
.t-mid{display:flex; flex-direction:column; gap:4px; min-width:0}
.t-tags{display:flex; align-items:center; gap:6px; flex-wrap:wrap}
.tag{padding:2px 8px; border-radius:5px; font-size:.65em; font-weight:700; font-family:'JetBrains Mono',monospace; letter-spacing:.3px}
.tag-tai{background:var(--blue-soft); color:var(--blue)}
.tag-xiu{background:var(--rose-soft); color:var(--rose)}
.t-meta{font-size:.68em; color:var(--text-faint); display:flex; gap:8px; align-items:center}
.t-dice{font-family:'JetBrains Mono',monospace; letter-spacing:.5px}
.t-result{text-align:right; display:flex; flex-direction:column; align-items:flex-end; gap:2px}
.t-result .status{font-size:.72em; font-weight:700; display:flex; align-items:center; gap:4px}
.t-result .time{font-size:.62em; color:var(--text-faint); font-family:'JetBrains Mono',monospace}

.empty{display:flex; flex-direction:column; align-items:center; justify-content:center; padding:64px 20px; color:var(--text-faint); gap:10px; text-align:center}
.empty svg{width:40px; height:40px; opacity:.4}
.empty .big{font-family:'JetBrains Mono',monospace; font-size:1.4em; font-weight:700; color:var(--text-dim)}

.foot{text-align:center; color:var(--text-faint); font-size:.7em; padding-top:6px; letter-spacing:.3px}
</style>
</head>
<body>
<div class="mesh"></div>
<div class="grain"></div>

<div class="shell">

  <header class="header">
    <div class="brand">
      <div class="brand-mark">
        <svg viewBox="0 0 24 24" fill="none"><path d="M12 2L3 7v10l9 5 9-5V7l-9-5z" stroke="white" stroke-width="1.6" stroke-linejoin="round"/><path d="M12 12l9-5M12 12v10M12 12L3 7" stroke="white" stroke-width="1.6" stroke-linejoin="round"/></svg>
      </div>
      <div class="brand-text">
        <div class="name">NEXUS<span style="color:var(--blue)">·</span>TX</div>
        <div class="tag">admin : trần dũng</div>
        <div class="tag">tiktok : @user111129</div>
      </div>
    </div>
    <div class="hud">
      <div class="game-selector" id="game-selector">
        {% for key, config in game_config.items() %}
          {% if config.active %}
            <button class="game-btn {{ key }} {% if key == current_game %}active{% endif %}" 
                    data-game="{{ key }}"
                    style="--accent: {{ config.color }}">
              {{ config.name }}
            </button>
          {% endif %}
        {% endfor %}
      </div>
      <div class="hud-item">
        <span class="hud-label">Cập nhật</span>
        <span class="hud-value mono" id="hud-time">--:--:--</span>
      </div>
      <a href="{{ game_config[current_game].bet_url }}" target="_blank" class="bet-btn">🎲 Đặt Cược</a>
      <div class="live-chip"><span class="live-dot"></span><span class="live-text">LIVE</span></div>
    </div>
  </header>

  <div class="dual-grid" id="dual-grid">
    <div id="hu-container">
      <div class="gcard">
        <div class="gcard-head">
          <span class="eyebrow">🟠Tài Xỉu Hũ</span>
        </div>
        <div class="hero" id="hu-hero">
          <div class="hero-top">
            <span>Ván vừa xong: <b id="hu-last-result">—</b></span>
            <span class="dice-chip" id="hu-last-dice"><span class="die mono">—</span></span>
          </div>
          <div class="hero-main">
            <div class="gauge-wrap">
              <svg viewBox="0 0 200 200">
                <circle class="gauge-track" cx="100" cy="100" r="85"/>
                <circle class="gauge-fill" id="hu-gauge" cx="100" cy="100" r="85" stroke="#ff8c42" stroke-dasharray="534.07" stroke-dashoffset="267"/>
              </svg>
              <div class="gauge-center">
                <span class="gauge-sub">Khuyến nghị</span>
                <span class="gauge-call display" id="hu-call">—</span>
                <span class="gauge-conf mono" id="hu-conf">0%</span>
              </div>
            </div>
            <div class="prob-cols">
              <div class="prob-row">
                <div class="prob-row-top">
                  <span class="prob-name" style="color:var(--orange)">TÀI</span>
                  <span class="prob-pct" id="hu-pct-tai" style="color:var(--orange)">50%</span>
                </div>
                <div class="prob-track"><div class="prob-fill" id="hu-bar-tai" style="width:50%; background:linear-gradient(90deg,#ff8c42,#ffb07c)"></div></div>
              </div>
              <div class="prob-row">
                <div class="prob-row-top">
                  <span class="prob-name" style="color:var(--rose)">XỈU</span>
                  <span class="prob-pct" id="hu-pct-xiu" style="color:var(--rose)">50%</span>
                </div>
                <div class="prob-track"><div class="prob-fill" id="hu-bar-xiu" style="width:50%; background:linear-gradient(90deg,#ff4d6d,#ff8fa3)"></div></div>
              </div>
            </div>
          </div>
          <div class="metric-strip">
            <div class="metric-cell"><div class="metric-num" id="hu-m-samples">0</div><div class="metric-lbl">Mẫu khớp</div></div>
            <div class="metric-cell"><div class="metric-num" id="hu-m-exact">0</div><div class="metric-lbl">Khớp chính xác</div></div>
            <div class="metric-cell"><div class="metric-num" id="hu-m-similar">0</div><div class="metric-lbl">Khớp tương đồng</div></div>
            <div class="metric-cell"><div class="metric-num" id="hu-m-conf">0%</div><div class="metric-lbl">Độ tin cậy</div></div>
          </div>
        </div>
        <div class="engine-stats" id="hu-engine">
          <div class="engine-stat"><span class="v mono" id="hu-es-similarity" style="color:var(--orange)">0%</span><span class="l">Độ tương đồng</span></div>
          <div class="engine-stat"><span class="v mono" id="hu-es-history">0</span><span class="l">Tổng lịch sử</span></div>
          <div class="engine-stat"><span class="v mono" id="hu-es-taixiu">0-0</span><span class="l">Tài-Xỉu</span></div>
          <div class="engine-stat"><span class="v mono" id="hu-es-signal">N/A</span><span class="l">Tín hiệu</span></div>
        </div>
      </div>
    </div>

    <div id="md5-container">
      <div class="gcard">
        <div class="gcard-head">
          <span class="eyebrow">🔷Tài Xỉu MD5</span>
        </div>
        <div class="hero" id="md5-hero">
          <div class="hero-top">
            <span>Ván vừa xong: <b id="md5-last-result">—</b></span>
            <span class="dice-chip" id="md5-last-dice"><span class="die mono">—</span></span>
          </div>
          <div class="hero-main">
            <div class="gauge-wrap">
              <svg viewBox="0 0 200 200">
                <circle class="gauge-track" cx="100" cy="100" r="85"/>
                <circle class="gauge-fill" id="md5-gauge" cx="100" cy="100" r="85" stroke="#3b9eff" stroke-dasharray="534.07" stroke-dashoffset="267"/>
              </svg>
              <div class="gauge-center">
                <span class="gauge-sub">Khuyến nghị</span>
                <span class="gauge-call display" id="md5-call">—</span>
                <span class="gauge-conf mono" id="md5-conf">0%</span>
              </div>
            </div>
            <div class="prob-cols">
              <div class="prob-row">
                <div class="prob-row-top">
                  <span class="prob-name" style="color:var(--blue)">TÀI</span>
                  <span class="prob-pct" id="md5-pct-tai" style="color:var(--blue)">50%</span>
                </div>
                <div class="prob-track"><div class="prob-fill" id="md5-bar-tai" style="width:50%; background:linear-gradient(90deg,#3b9eff,#7cc1ff)"></div></div>
              </div>
              <div class="prob-row">
                <div class="prob-row-top">
                  <span class="prob-name" style="color:var(--rose)">XỈU</span>
                  <span class="prob-pct" id="md5-pct-xiu" style="color:var(--rose)">50%</span>
                </div>
                <div class="prob-track"><div class="prob-fill" id="md5-bar-xiu" style="width:50%; background:linear-gradient(90deg,#ff4d6d,#ff8fa3)"></div></div>
              </div>
            </div>
          </div>
          <div class="metric-strip">
            <div class="metric-cell"><div class="metric-num" id="md5-m-samples">0</div><div class="metric-lbl">Mẫu khớp</div></div>
            <div class="metric-cell"><div class="metric-num" id="md5-m-exact">0</div><div class="metric-lbl">Khớp chính xác</div></div>
            <div class="metric-cell"><div class="metric-num" id="md5-m-similar">0</div><div class="metric-lbl">Khớp tương đồng</div></div>
            <div class="metric-cell"><div class="metric-num" id="md5-m-conf">0%</div><div class="metric-lbl">Độ tin cậy</div></div>
          </div>
        </div>
        <div class="engine-stats" id="md5-engine">
          <div class="engine-stat"><span class="v mono" id="md5-es-similarity" style="color:var(--blue)">0%</span><span class="l">Độ tương đồng</span></div>
          <div class="engine-stat"><span class="v mono" id="md5-es-history">0</span><span class="l">Tổng lịch sử</span></div>
          <div class="engine-stat"><span class="v mono" id="md5-es-taixiu">0-0</span><span class="l">Tài-Xỉu</span></div>
          <div class="engine-stat"><span class="v mono" id="md5-es-signal">N/A</span><span class="l">Tín hiệu</span></div>
        </div>
      </div>
    </div>
  </div>

  <div class="gcard" style="margin-bottom:18px">
    <div class="gcard-head">
      <span class="eyebrow">📊 Thống kê tổng hợp</span>
    </div>
    <div class="stats-grid" id="stats-grid">
      <div class="stat-box"><span class="v mono" id="s-hu-winrate" style="color:var(--emerald)">0%</span><span class="l">Hũ Winrate</span></div>
      <div class="stat-box"><span class="v mono" id="s-md5-winrate" style="color:var(--emerald)">0%</span><span class="l">MD5 Winrate</span></div>
      <div class="stat-box"><span class="v mono" id="s-hu-total">0</span><span class="l">Hũ Dự đoán</span></div>
      <div class="stat-box"><span class="v mono" id="s-md5-total">0</span><span class="l">MD5 Dự đoán</span></div>
    </div>
  </div>

  <div class="gcard">
    <div class="gcard-head">
      <span class="eyebrow">📜 Lịch sử dự đoán</span>
      <span class="eyebrow" style="color:var(--text-faint)" id="hist-count">0 ván</span>
    </div>
    <div class="timeline" id="timeline">
      <div class="empty">
        <svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.4"/><path d="M12 8v4l2.5 1.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
        <span>Chưa có dữ liệu</span>
      </div>
    </div>
  </div>

  <footer class="foot">NEXUS·TX · Dice History Retrieval Engine</footer>
</div>

<script>
const GAUGE_CIRC = 534.07;

function updateType(type, data) {
  console.log('🔄 Updating', type, 'Data:', data);
  
  // Nếu không có dữ liệu hoặc data rỗng
  if (!data) {
    document.getElementById(type + '-call').textContent = 'Đang thu thập...';
    return;
  }
  
  // Kiểm tra tong_so_van
  if (!data.tong_so_van || data.tong_so_van < 5) {
    document.getElementById(type + '-call').textContent = 'Đang thu thập...';
    console.log('⚠️ ' + type + ': tong_so_van =', data.tong_so_van);
    return;
  }
  
  console.log('✅ ' + type + ': tong_so_van =', data.tong_so_van, 'Prediction:', data.khuyen_nghi);
  
  const prefix = type;
  const isTai = data.khuyen_nghi === 'TAI';
  const isXiu = data.khuyen_nghi === 'XIU';
  const isNoSignal = data.khuyen_nghi === 'NO SIGNAL' || data.khuyen_nghi === 'CHUA_DU_DU_LIEU';
  const prob = isTai ? data.xac_suat_tai : (isXiu ? data.xac_suat_xiu : 0.5);
  const callColor = isTai ? '#3b9eff' : (isXiu ? '#ff4d6d' : (isNoSignal ? '#ffb454' : '#ffb454'));
  
  // Cập nhật gauge
  const gauge = document.getElementById(prefix + '-gauge');
  if (gauge) {
    gauge.setAttribute('stroke', callColor);
    gauge.setAttribute('stroke-dashoffset', GAUGE_CIRC * (1 - prob));
  }
  
  // Cập nhật khuyến nghị
  const callEl = document.getElementById(prefix + '-call');
  if (callEl) {
    callEl.textContent = data.khuyen_nghi === 'NO SIGNAL' ? '⏸️ NO SIGNAL' : 
                         data.khuyen_nghi === 'CHUA_DU_DU_LIEU' ? '⏳ ĐANG THU THẬP' :
                         data.khuyen_nghi === 'CÂN NHẮC' ? '⚖️ CÂN NHẮC' : data.khuyen_nghi;
    callEl.style.color = callColor;
  }
  
  // Cập nhật các thông số
  document.getElementById(prefix + '-conf').textContent = (data.do_tin_cay_so || 0) + '%';
  document.getElementById(prefix + '-pct-tai').textContent = (data.xac_suat_tai * 100).toFixed(1) + '%';
  document.getElementById(prefix + '-pct-xiu').textContent = (data.xac_suat_xiu * 100).toFixed(1) + '%';
  document.getElementById(prefix + '-bar-tai').style.width = (data.xac_suat_tai * 100) + '%';
  document.getElementById(prefix + '-bar-xiu').style.width = (data.xac_suat_xiu * 100) + '%';
  
  document.getElementById(prefix + '-m-samples').textContent = data.samples || 0;
  document.getElementById(prefix + '-m-exact').textContent = data.exact_samples || 0;
  document.getElementById(prefix + '-m-similar').textContent = data.similar_samples || 0;
  document.getElementById(prefix + '-m-conf').textContent = (data.do_tin_cay_so || 0) + '%';
  
  document.getElementById(prefix + '-es-similarity').textContent = (data.similarity_score || 0) + '%';
  document.getElementById(prefix + '-es-history').textContent = data.tong_so_van || 0;
  document.getElementById(prefix + '-es-taixiu').textContent = (data.so_tai || 0) + '-' + (data.so_xiu || 0);
  
  const signalEl = document.getElementById(prefix + '-es-signal');
  if (data.signal === 'NO_SIGNAL') {
    signalEl.textContent = '⏸️ N/A';
    signalEl.style.color = '#ffb454';
  } else if (data.signal === 'TAI') {
    signalEl.textContent = '⬆️ TÀI';
    signalEl.style.color = '#3b9eff';
  } else if (data.signal === 'XIU') {
    signalEl.textContent = '⬇️ XỈU';
    signalEl.style.color = '#ff4d6d';
  } else {
    signalEl.textContent = data.signal || 'N/A';
  }
  
  document.getElementById(prefix + '-last-result').textContent = data.ket_qua_hien_tai || '—';
  
  const diceContainer = document.getElementById(prefix + '-last-dice');
  if (data.last_dice && data.last_dice.length > 0) {
    diceContainer.innerHTML = data.last_dice.map(d => `<span class="die mono">${d}</span>`).join('');
  } else {
    diceContainer.innerHTML = '<span class="die mono">—</span>';
  }
}

function updateStats(data) {
  if (!data) return;
  document.getElementById('s-hu-winrate').textContent = (data.hu?.thong_ke_tong_hop?.ty_le_thang || 0) + '%';
  document.getElementById('s-md5-winrate').textContent = (data.md5?.thong_ke_tong_hop?.ty_le_thang || 0) + '%';
  document.getElementById('s-hu-total').textContent = data.hu?.thong_ke_tong_hop?.tong_du_doan || 0;
  document.getElementById('s-md5-total').textContent = data.md5?.thong_ke_tong_hop?.tong_du_doan || 0;
  
  if (data.hu?.thoi_gian_cap_nhat || data.md5?.thoi_gian_cap_nhat) {
    document.getElementById('hud-time').textContent = data.hu?.thoi_gian_cap_nhat || data.md5?.thoi_gian_cap_nhat || '--:--:--';
  }
}

function renderTimeline(history) {
  const wrap = document.getElementById('timeline');
  if (!wrap) return;
  
  if (!history || !history.length) {
    wrap.innerHTML = `<div class="empty"><svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.4"/><path d="M12 8v4l2.5 1.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg><span>Chưa có dữ liệu</span></div>`;
    return;
  }
  
  wrap.innerHTML = history.slice().reverse().slice(0, 30).map(item => {
    const winColor = item.dung ? '#2bd97c' : '#ff4d6d';
    const statusIcon = item.dung ? '✅ THẮNG' : '❌ THUA';
    const typeLabel = item.loai === 'hu' ? '🟠Hũ' : '🔷MD5';
    return `
      <div class="t-row">
        <div class="t-rail">
          <div class="t-dot" style="background:${winColor}; color:${winColor}"></div>
          <div class="t-line"></div>
        </div>
        <div class="t-mid">
          <div class="t-tags">
            <span class="tag ${item.du_doan === 'TAI' ? 'tag-tai' : 'tag-xiu'}">${item.du_doan}</span>
            <span style="font-size:.6em;color:var(--text-faint)">→</span>
            <span class="tag ${item.ket_qua === 'TAI' ? 'tag-tai' : 'tag-xiu'}">${item.ket_qua}</span>
            <span style="font-size:.55em;color:var(--text-faint);font-family:'JetBrains Mono',monospace">${typeLabel}</span>
          </div>
          <div class="t-meta"><span class="t-dice mono">${item.xuc_xac || ''}</span></div>
        </div>
        <div class="t-result">
          <span class="status" style="color:${winColor}">${statusIcon}</span>
          <span class="time">${item.thoi_gian}</span>
        </div>
      </div>
    `;
  }).join('');
  document.getElementById('hist-count').textContent = history.length + ' ván';
}

// Game switching
document.querySelectorAll('.game-btn').forEach(btn => {
  btn.addEventListener('click', async function() {
    const game = this.dataset.game;
    if (this.classList.contains('active')) return;
    
    try {
      const res = await fetch('/api/switch_game', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({game: game})
      });
      const data = await res.json();
      if (data.success) {
        document.querySelectorAll('.game-btn').forEach(b => b.classList.remove('active'));
        this.classList.add('active');
        await fetchData();
        const betBtn = document.querySelector('.bet-btn');
        if (betBtn) {
          const configs = {{ game_config|tojson }};
          betBtn.href = configs[game].bet_url;
        }
        location.reload();
      }
    } catch(e) {
      console.error('Switch game error:', e);
    }
  });
});

async function fetchData() {
  try {
    const res = await fetch('/api/all', {cache:'no-store'});
    if (!res.ok) return;
    const data = await res.json();
    console.log('📊 Data received:', data);
    
    // Cập nhật từng loại
    if (data.hu) {
      console.log('✅ HU tong_so_van:', data.hu.du_doan_van_tiep?.tong_so_van);
      updateType('hu', data.hu.du_doan_van_tiep);
    }
    if (data.md5) {
      console.log('✅ MD5 tong_so_van:', data.md5.du_doan_van_tiep?.tong_so_van);
      updateType('md5', data.md5.du_doan_van_tiep);
    }
    
    updateStats(data);
    
    const allHistory = [];
    if (data.hu?.lich_su_dung_sai) {
      data.hu.lich_su_dung_sai.forEach(h => { h.loai = 'hu'; allHistory.push(h); });
    }
    if (data.md5?.lich_su_dung_sai) {
      data.md5.lich_su_dung_sai.forEach(h => { h.loai = 'md5'; allHistory.push(h); });
    }
    allHistory.sort((a,b) => a.thoi_gian?.localeCompare(b.thoi_gian));
    renderTimeline(allHistory);
  } catch(e) {
    console.error('❌ Fetch error:', e);
  }
}

// Fetch data immediately and every 3 seconds
fetchData();
setInterval(fetchData, 3000);
</script>
</body>
</html>
"""

# ======= MAIN =======
if __name__ == '__main__':
    logging.info("🚀 Khởi động NEXUS·TX với Dice History Retrieval Engine...")
    logging.info("🔑 Đã cấu hình Authorization Bearer Token")
    logging.info("📊 Engine phân tích dựa trên lịch sử xúc xắc")
    logging.info(f"🎮 Game hiện tại: {GAME_CONFIG[current_game]['name']}")
    # Cho Render
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)