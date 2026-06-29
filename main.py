# app_lc.py - Dùng Application (phiên bản 20.x)
import requests
import json
import threading
import time
from collections import deque
import logging
import math
from datetime import datetime
import statistics
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ======= CẤU HÌNH =======
TOKEN = "8832398152:AAEAHSHUhbGeriCakvqwpfAqKYYyEG6yXFI"  # Nên đổi token mới!

GAME_CONFIG = {
    'lc79': {
        'name': 'LC79',
        'color': '#ff6b35',
        'md5_url': 'https://wtxmd52.tele68.com/v1/txmd5/sessions?cp=R&cl=R&pf=web&at=7e3955a9b92d0a12a675097596748258',
        'hu_url': 'https://wtx.tele68.com/v1/tx/sessions?cp=R&cl=R&pf=web&at=4a79fe6ffe00c22102db76778b434c50',
        'bet_url': 'https://lc79.bet',
        'active': True
    }
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
        },
        "hieu_suat_phuong_phap": {
            "markov": deque(maxlen=50),
            "fft": deque(maxlen=50),
            "ml": deque(maxlen=50),
            "bayes": deque(maxlen=50),
            "pattern": deque(maxlen=50)
        }
    }

du_lieu = {}

def khoi_tao_du_lieu():
    global du_lieu
    du_lieu = {
        "hu": tao_cau_truc_loai(),
        "md5": tao_cau_truc_loai()
    }

khoi_tao_du_lieu()

# ======= LẤY DỮ LIỆU =======
def lay_toan_bo_lich_su(url):
    for attempt in range(3):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            r = requests.get(url, timeout=5, headers=headers)
            r.raise_for_status()
            data = r.json()
            if 'list' in data and len(data['list']) > 0:
                return data['list']
        except requests.exceptions.RequestException as e:
            logging.warning(f"Attempt {attempt+1}/3 failed for {url}: {e}")
            if attempt < 2:
                time.sleep(2)
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            if attempt < 2:
                time.sleep(2)
    return []

# ======= 5 PHƯƠNG PHÁP PHÂN TÍCH =======
def phan_tich_5_phuong_phap(danh_sach, loai=""):
    if not danh_sach or len(danh_sach) < 15:
        return tao_du_doan_mac_dinh(danh_sach, loai)
    
    van_hien_tai = danh_sach[0]
    lich_su = danh_sach[1:]
    
    ket_qua = [p['resultTruyenThong'] for p in lich_su]
    diem = [p['point'] for p in lich_su]
    tong_van = len(ket_qua)
    
    mang_so = [1 if k == 'TAI' else 0 for k in ket_qua]
    
    def markov_bac_3_can_bang(mang):
        if len(mang) < 5:
            return 0.5
        
        pattern = tuple(mang[:3])
        dem_tai = 0
        dem_xiu = 0
        
        for i in range(len(mang) - 3):
            if tuple(mang[i:i+3]) == pattern:
                if i + 3 < len(mang):
                    if mang[i+3] == 1:
                        dem_tai += 1
                    else:
                        dem_xiu += 1
        
        tong = dem_tai + dem_xiu
        if tong > 0:
            return dem_tai / tong
        return 0.5
    
    p_markov = markov_bac_3_can_bang(mang_so)
    
    def phat_hien_chu_ky_can_bang(mang):
        if len(mang) < 15:
            return 0.5
        
        chu_ky_tot_nhat = 2
        do_chinh_xac_cao_nhat = 0
        
        for chu_ky in range(2, min(11, len(mang)//2)):
            dung = 0
            tong = 0
            for i in range(len(mang) - chu_ky):
                if mang[i] == mang[i + chu_ky]:
                    dung += 1
                tong += 1
            
            do_chinh_xac = dung / tong if tong > 0 else 0
            if do_chinh_xac > do_chinh_xac_cao_nhat:
                do_chinh_xac_cao_nhat = do_chinh_xac
                chu_ky_tot_nhat = chu_ky
        
        if do_chinh_xac_cao_nhat > 0.55:
            vi_tri = len(mang) % chu_ky_tot_nhat
            if vi_tri < len(mang):
                return mang[vi_tri]
        
        return 0.5
    
    p_chu_ky = phat_hien_chu_ky_can_bang(mang_so)
    
    def ml_don_gian_can_bang(mang, diem):
        if len(mang) < 15:
            return 0.5
        
        features = []
        labels = []
        
        for i in range(len(mang) - 5):
            f = [
                sum(mang[i:i+5]) / 5,
                sum(mang[max(0,i-5):i+1]) / min(6, i+1),
                diem[i] / 18 if i < len(diem) else 0.5,
                statistics.mean(mang[max(0,i-10):i+1]) if i >= 5 else 0.5
            ]
            features.append(f)
            labels.append(mang[i+5])
        
        if len(features) < 5:
            return 0.5
        
        def hoi_quy(X, y):
            n = len(X)
            if n == 0:
                return [0, 0, 0, 0], 0
            X_mean = [sum(x[j] for x in X)/n for j in range(4)]
            y_mean = sum(y)/n
            
            tu_so = [0, 0, 0, 0]
            mau_so = [0, 0, 0, 0]
            
            for i in range(n):
                for j in range(4):
                    tu_so[j] += (X[i][j] - X_mean[j]) * (y[i] - y_mean)
                    mau_so[j] += (X[i][j] - X_mean[j]) ** 2
            
            he_so = [tu_so[j] / (mau_so[j] + 0.001) for j in range(4)]
            intercept = y_mean - sum(he_so[j] * X_mean[j] for j in range(4))
            
            return he_so, intercept
        
        he_so, intercept = hoi_quy(features, labels)
        
        feature_moi = [
            sum(mang[-5:]) / 5,
            sum(mang[-6:]) / 6,
            diem[0] / 18 if diem else 0.5,
            statistics.mean(mang[-10:]) if len(mang) >= 10 else 0.5
        ]
        
        du_doan = intercept + sum(he_so[j] * feature_moi[j] for j in range(4))
        return max(0.1, min(0.9, du_doan))
    
    p_ml = ml_don_gian_can_bang(mang_so, diem)
    
    def bayesian_can_bang(diem, ket_qua):
        if len(diem) < 10:
            return 0.5
        
        diem_tai = [d for d, k in zip(diem, ket_qua) if k == 'TAI']
        diem_xiu = [d for d, k in zip(diem, ket_qua) if k == 'XIU']
        
        if not diem_tai or not diem_xiu:
            return 0.5
        
        tb_tai = statistics.mean(diem_tai)
        tb_xiu = statistics.mean(diem_xiu)
        std_tai = statistics.stdev(diem_tai) if len(diem_tai) > 1 else 1
        std_xiu = statistics.stdev(diem_xiu) if len(diem_xiu) > 1 else 1
        
        p_prior_tai = len(diem_tai) / len(diem)
        p_prior_xiu = len(diem_xiu) / len(diem)
        
        diem_hien_tai = diem[0] if diem else 10.5
        
        def normal_pdf(x, mean, std):
            if std == 0:
                return 0
            return (1/(std * math.sqrt(2*math.pi))) * math.exp(-0.5*((x-mean)/std)**2)
        
        likelihood_tai = normal_pdf(diem_hien_tai, tb_tai, std_tai)
        likelihood_xiu = normal_pdf(diem_hien_tai, tb_xiu, std_xiu)
        
        posterior_tai = likelihood_tai * p_prior_tai
        posterior_xiu = likelihood_xiu * p_prior_xiu
        
        tong = posterior_tai + posterior_xiu
        if tong > 0:
            return posterior_tai / tong
        return 0.5
    
    p_bayes = bayesian_can_bang(diem, ket_qua)
    
    def pattern_matching_can_bang(mang, window=5):
        if len(mang) < window * 2:
            return 0.5
        
        pattern_hien_tai = mang[:window]
        ket_qua_pattern = []
        
        for i in range(len(mang) - window):
            pattern_cu = mang[i:i+window]
            khop = sum(1 for a, b in zip(pattern_hien_tai, pattern_cu) if a == b)
            ty_le_khop = khop / window
            
            if ty_le_khop >= 0.6 and i + window < len(mang):
                ket_qua_pattern.append((ty_le_khop, mang[i+window]))
        
        if ket_qua_pattern:
            tong_trong_so = sum(k[0] for k in ket_qua_pattern)
            if tong_trong_so > 0:
                du_doan = sum(k[0] * k[1] for k in ket_qua_pattern) / tong_trong_so
                return du_doan
        
        return 0.5
    
    p_pattern = pattern_matching_can_bang(mang_so)
    
    def tinh_trong_so_dong(loai):
        hieu_suat = du_lieu[loai]['hieu_suat_phuong_phap'] if loai in du_lieu else None
        
        trong_so_mac_dinh = {
            'markov': 0.20,
            'fft': 0.15,
            'ml': 0.25,
            'bayes': 0.20,
            'pattern': 0.20
        }
        
        if not hieu_suat:
            return trong_so_mac_dinh
        
        tong_mau = sum(len(v) for v in hieu_suat.values())
        if tong_mau < 30:
            return trong_so_mac_dinh
        
        diem_phuong_phap = {}
        for ten, lich_su in hieu_suat.items():
            if len(lich_su) > 0:
                ty_le_dung = sum(1 for x in lich_su if x) / len(lich_su)
                he_so_tin_cay = min(1, len(lich_su) / 20)
                diem_phuong_phap[ten] = ty_le_dung * he_so_tin_cay
            else:
                diem_phuong_phap[ten] = 0.5
        
        tong_diem = sum(diem_phuong_phap.values())
        if tong_diem > 0:
            trong_so = {k: v/tong_diem for k, v in diem_phuong_phap.items()}
            return trong_so
        
        return trong_so_mac_dinh
    
    w = tinh_trong_so_dong(loai)
    
    p_tai = (
        p_markov * w.get('markov', 0.20) +
        p_chu_ky * w.get('fft', 0.15) +
        p_ml * w.get('ml', 0.25) +
        p_bayes * w.get('bayes', 0.20) +
        p_pattern * w.get('pattern', 0.20)
    )
    
    p_tai = max(0.05, min(0.95, p_tai))
    p_xiu = 1 - p_tai
    
    if loai == 'md5':
        nguong = 0.58
        nguong_can_nhac = 0.52
    else:
        nguong = 0.53
        nguong_can_nhac = 0.50
    
    chenh_lech = abs(p_tai - 0.5)
    do_tin_cay_co_so = min(95, 25 + chenh_lech * 300 + (tong_van / 20))
    
    if loai == 'md5':
        lich_su_gan_day = list(du_lieu[loai]['lich_su_dung_sai'])[-20:]
        if len(lich_su_gan_day) >= 10:
            ty_le_gan_day = sum(1 for x in lich_su_gan_day if x['dung']) / len(lich_su_gan_day)
            if ty_le_gan_day < 0.4:
                nguong = max(nguong, 0.62)
                do_tin_cay_co_so = max(10, do_tin_cay_co_so - 20)
    
    if p_tai >= nguong:
        khuyen = 'TAI'
        do_tin = 'Cao' if p_tai >= 0.65 else 'Trung bình'
    elif p_xiu >= nguong:
        khuyen = 'XIU'
        do_tin = 'Cao' if p_xiu >= 0.65 else 'Trung bình'
    elif chenh_lech < nguong_can_nhac:
        khuyen = 'CAN_NHAC'
        do_tin = 'Thap'
    else:
        khuyen = 'THAN_TRONG'
        do_tin = 'Thap'
    
    chuoi = [van_hien_tai['resultTruyenThong']] + ket_qua
    chuoi_hien_tai = 1
    for i in range(1, len(chuoi)):
        if chuoi[i] == chuoi[i-1]:
            chuoi_hien_tai += 1
        else:
            break
    
    so_tai = ket_qua.count('TAI')
    so_xiu = ket_qua.count('XIU')
    
    cac_pp = [
        ('Markov Bậc 3', p_markov, w.get('markov', 0.20)),
        ('Phân Tích Chu Kỳ', p_chu_ky, w.get('fft', 0.15)),
        ('Machine Learning', p_ml, w.get('ml', 0.25)),
        ('Bayesian Điểm Số', p_bayes, w.get('bayes', 0.20)),
        ('Pattern Matching', p_pattern, w.get('pattern', 0.20))
    ]
    
    return {
        'khuyen_nghi': khuyen,
        'xac_suat_tai': round(p_tai, 4),
        'xac_suat_xiu': round(p_xiu, 4),
        'do_tin_cay': do_tin,
        'do_tin_cay_so': round(do_tin_cay_co_so, 1),
        'van_gan_nhat': van_hien_tai,
        'chieu_dai_chuoi': chuoi_hien_tai,
        'ket_qua_hien_tai': van_hien_tai['resultTruyenThong'],
        'tong_so_van': tong_van,
        'so_tai': so_tai,
        'so_xiu': so_xiu,
        'p_markov': p_markov,
        'p_chu_ky': p_chu_ky,
        'p_ml': p_ml,
        'p_bayes': p_bayes,
        'p_pattern': p_pattern,
        'trong_so': w,
        'nguong': nguong
    }

def tao_du_doan_mac_dinh(danh_sach, loai=""):
    van_gan = danh_sach[0] if danh_sach else None
    return {
        'khuyen_nghi': 'CHUA_DU_DU_LIEU',
        'xac_suat_tai': 0.5,
        'xac_suat_xiu': 0.5,
        'do_tin_cay': 'Thap',
        'do_tin_cay_so': 10,
        'van_gan_nhat': van_gan,
        'chieu_dai_chuoi': 0,
        'ket_qua_hien_tai': van_gan['resultTruyenThong'] if van_gan else None,
        'tong_so_van': len(danh_sach),
        'so_tai': 0,
        'so_xiu': 0,
        'p_markov': 0.5, 'p_chu_ky': 0.5, 'p_ml': 0.5,
        'p_bayes': 0.5, 'p_pattern': 0.5,
        'trong_so': {'markov':0.20, 'fft':0.15, 'ml':0.25, 'bayes':0.20, 'pattern':0.20},
        'nguong': 0.58 if loai == 'md5' else 0.53
    }

# ======= CẬP NHẬT HIỆU SUẤT =======
def cap_nhat_hieu_suat(du_doan, ket_qua_thuc, loai):
    if not du_doan or ket_qua_thuc not in ['TAI', 'XIU']:
        return
    
    ket_qua_so = 1 if ket_qua_thuc == 'TAI' else 0
    hieu_suat = du_lieu[loai]['hieu_suat_phuong_phap']
    
    methods = [
        ('markov', du_doan.get('p_markov', 0.5)),
        ('fft', du_doan.get('p_chu_ky', 0.5)),
        ('ml', du_doan.get('p_ml', 0.5)),
        ('bayes', du_doan.get('p_bayes', 0.5)),
        ('pattern', du_doan.get('p_pattern', 0.5))
    ]
    
    for name, p in methods:
        du_doan_pp = 1 if p >= 0.5 else 0
        hieu_suat[name].append(du_doan_pp == ket_qua_so)

# ======= HÀM ĐỊNH DẠNG XÚC XẮC =======
def dinh_dang_xuc_xac(van):
    if not van:
        return ''
    xx = van.get('dices')
    if isinstance(xx, (list, tuple)) and len(xx) > 0:
        return '-'.join(str(x) for x in xx)
    return str(van.get('point', ''))

# ======= CẬP NHẬT DỮ LIỆU =======
def cap_nhat_loai(loai, url):
    data = du_lieu[loai]
    
    while True:
        try:
            danh_sach = lay_toan_bo_lich_su(url)
            if not danh_sach:
                time.sleep(2)
                continue
            
            data['toan_bo_lich_su'] = danh_sach
            van_gan = danh_sach[0]
            van_id = van_gan.get('id')
            
            if data['lan_cap_nhat_truoc'] is None or data['lan_cap_nhat_truoc'] != van_id:
                if data['du_doan_van_tiep'] and data['van_gan_nhat']:
                    du_doan_cu = data['du_doan_van_tiep']['khuyen_nghi']
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
                        
                        cap_nhat_hieu_suat(data['du_doan_van_tiep'], ket_qua_thuc, loai)
                
                data['van_gan_nhat'] = van_gan
                data['du_doan_van_tiep'] = phan_tich_5_phuong_phap(danh_sach, loai)
                data['lan_cap_nhat_truoc'] = van_id
                data['thoi_gian_cap_nhat'] = datetime.now().strftime('%H:%M:%S')
                
        except Exception as e:
            logging.error(f"Lỗi cập nhật {loai}: {e}")
        
        time.sleep(2)

def start_updater():
    """Khởi động updater cho LC79"""
    config = GAME_CONFIG['lc79']
    khoi_tao_du_lieu()
    threading.Thread(target=cap_nhat_loai, args=('hu', config['hu_url']), daemon=True).start()
    threading.Thread(target=cap_nhat_loai, args=('md5', config['md5_url']), daemon=True).start()
    logging.info("🔄 Đã khởi động LC79 Bot")

# ======= BOT TELEGRAM (Dùng Application) =======
def format_du_doan(loai, data, game_name="LC79"):
    if not data or data.get('khuyen_nghi') == 'CHUA_DU_DU_LIEU':
        return f"⏳ {game_name} - {loai.upper()}: Đang thu thập dữ liệu..."
    
    emoji = "🔴" if data['khuyen_nghi'] == 'TAI' else "🔵" if data['khuyen_nghi'] == 'XIU' else "⚪"
    
    msg = f"""
🎲 **{game_name} - {loai.upper()}**
━━━━━━━━━━━━━━━━━
{emoji} **Khuyến nghị:** `{data['khuyen_nghi']}`
📊 **Tài:** {data['xac_suat_tai']*100:.1f}%
📊 **Xỉu:** {data['xac_suat_xiu']*100:.1f}%
🎯 **Độ tin cậy:** {data['do_tin_cay_so']}% ({data['do_tin_cay']})

📈 **Thống kê:**
• Chuỗi: {data['chieu_dai_chuoi']} ván
• Tài-Xỉu: {data['so_tai']}–{data['so_xiu']}
• Tổng: {data['tong_so_van']} ván

🧠 **Các phương pháp:**
• Markov: {data['p_markov']*100:.1f}%
• Chu kỳ: {data['p_chu_ky']*100:.1f}%
• ML: {data['p_ml']*100:.1f}%
• Bayesian: {data['p_bayes']*100:.1f}%
• Pattern: {data['p_pattern']*100:.1f}%
━━━━━━━━━━━━━━━━━
🕐 Cập nhật: {du_lieu[loai]['thoi_gian_cap_nhat'] or '--:--:--'}
"""
    return msg

def format_thong_ke():
    msg = f"""
📊 **THỐNG KÊ TỔNG HỢP LC79**
━━━━━━━━━━━━━━━━━
🟠 **Tài Xỉu HŨ:**
• Dự đoán: {du_lieu['hu']['thong_ke_tong_hop']['tong_du_doan']}
• Đúng: {du_lieu['hu']['thong_ke_tong_hop']['tong_dung']}
• Sai: {du_lieu['hu']['thong_ke_tong_hop']['tong_sai']}
• Tỷ lệ thắng: {du_lieu['hu']['thong_ke_tong_hop']['ty_le_thang']}%

🔷 **Tài Xỉu MD5:**
• Dự đoán: {du_lieu['md5']['thong_ke_tong_hop']['tong_du_doan']}
• Đúng: {du_lieu['md5']['thong_ke_tong_hop']['tong_dung']}
• Sai: {du_lieu['md5']['thong_ke_tong_hop']['tong_sai']}
• Tỷ lệ thắng: {du_lieu['md5']['thong_ke_tong_hop']['ty_le_thang']}%
━━━━━━━━━━━━━━━━━
"""
    return msg

def format_lich_su():
    history = []
    for item in du_lieu['hu']['lich_su_dung_sai']:
        item['loai'] = 'HU'
        history.append(item)
    for item in du_lieu['md5']['lich_su_dung_sai']:
        item['loai'] = 'MD5'
        history.append(item)
    
    history = sorted(history, key=lambda x: x['thoi_gian'], reverse=True)[:10]
    
    if not history:
        return "📜 Chưa có lịch sử dự đoán"
    
    msg = "📜 **LỊCH SỬ DỰ ĐOÁN (10 gần nhất)**\n━━━━━━━━━━━━━━━━━\n"
    for item in history:
        status = "✅" if item['dung'] else "❌"
        msg += f"{status} {item['loai']} | DĐ: {item['du_doan']} → KT: {item['ket_qua']} | {item['thoi_gian']}\n"
        if item.get('xuc_xac'):
            msg += f"   🎲 {item['xuc_xac']}\n"
    return msg

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🟠 Dự đoán HŨ", callback_data='hu')],
        [InlineKeyboardButton("🔷 Dự đoán MD5", callback_data='md5')],
        [InlineKeyboardButton("📊 Thống kê", callback_data='stats')],
        [InlineKeyboardButton("📜 Lịch sử", callback_data='history')],
        [InlineKeyboardButton("🔄 Cập nhật", callback_data='refresh')],
        [InlineKeyboardButton("🎲 Đặt cược LC79", url='https://lc79.bet')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = """
🎲 **LC79 Tài Xỉu Bot** 
━━━━━━━━━━━━━━━━━
🧠 Phân tích bằng **5 phương pháp**:
• Markov Bậc 3
• Phân tích Chu kỳ
• Machine Learning
• Bayesian Điểm Số
• Pattern Matching

📈 **Ngưỡng:**
• HŨ: 53%
• MD5: 58%

🤖 Admin: @user111129
━━━━━━━━━━━━━━━━━
📌 Chọn chức năng bên dưới:
"""
    await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode='Markdown')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'hu':
        data = du_lieu['hu']['du_doan_van_tiep']
        msg = format_du_doan('hu', data, "LC79")
    elif query.data == 'md5':
        data = du_lieu['md5']['du_doan_van_tiep']
        msg = format_du_doan('md5', data, "LC79")
    elif query.data == 'stats':
        msg = format_thong_ke()
    elif query.data == 'history':
        msg = format_lich_su()
    elif query.data == 'refresh':
        msg = "🔄 Đã cập nhật dữ liệu mới nhất!"
        keyboard = [
            [InlineKeyboardButton("🟠 Dự đoán HŨ", callback_data='hu')],
            [InlineKeyboardButton("🔷 Dự đoán MD5", callback_data='md5')],
            [InlineKeyboardButton("📊 Thống kê", callback_data='stats')],
            [InlineKeyboardButton("📜 Lịch sử", callback_data='history')],
            [InlineKeyboardButton("🔄 Cập nhật", callback_data='refresh')],
            [InlineKeyboardButton("🎲 Đặt cược LC79", url='https://lc79.bet')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode='Markdown')
        return
    
    keyboard = [
        [InlineKeyboardButton("🟠 Dự đoán HŨ", callback_data='hu')],
        [InlineKeyboardButton("🔷 Dự đoán MD5", callback_data='md5')],
        [InlineKeyboardButton("📊 Thống kê", callback_data='stats')],
        [InlineKeyboardButton("📜 Lịch sử", callback_data='history')],
        [InlineKeyboardButton("🔄 Cập nhật", callback_data='refresh')],
        [InlineKeyboardButton("🎲 Đặt cược LC79", url='https://lc79.bet')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = """
📖 **Hướng dẫn sử dụng Bot LC79**

🔹 **Các lệnh:**
• /start - Hiển thị menu chính
• /hu - Dự đoán HŨ
• /md5 - Dự đoán MD5
• /stats - Thống kê tổng hợp
• /history - Lịch sử dự đoán
• /help - Hướng dẫn này

🔹 **Các nút bấm:**
• 🟠 Dự đoán HŨ - Xem dự đoán Tài Xỉu HŨ
• 🔷 Dự đoán MD5 - Xem dự đoán Tài Xỉu MD5
• 📊 Thống kê - Xem tỷ lệ thắng
• 📜 Lịch sử - Xem 10 dự đoán gần nhất
• 🔄 Cập nhật - Làm mới dữ liệu
• 🎲 Đặt cược - Đến trang đặt cược LC79

📌 **Ngưỡng dự đoán:**
• HŨ: ≥53% mới đưa ra khuyến nghị
• MD5: ≥58% mới đưa ra khuyến nghị
"""
    await update.message.reply_text(msg, parse_mode='Markdown')

async def hu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = du_lieu['hu']['du_doan_van_tiep']
    msg = format_du_doan('hu', data, "LC79")
    await update.message.reply_text(msg, parse_mode='Markdown')

async def md5_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = du_lieu['md5']['du_doan_van_tiep']
    msg = format_du_doan('md5', data, "LC79")
    await update.message.reply_text(msg, parse_mode='Markdown')

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = format_thong_ke()
    await update.message.reply_text(msg, parse_mode='Markdown')

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = format_lich_su()
    await update.message.reply_text(msg, parse_mode='Markdown')

def main():
    start_updater()
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("hu", hu_command))
    app.add_handler(CommandHandler("md5", md5_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    logging.info("🚀 LC79 Bot đang chạy...")
    app.run_polling()

if __name__ == "__main__":
    main()