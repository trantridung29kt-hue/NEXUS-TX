from flask import Flask, render_template_string, jsonify
import requests
import json
import threading
import time
from collections import deque
import logging
import math
from datetime import datetime
import statistics

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ======= CẤU HÌNH =======
URL_MD5 = "https://wtxmd52.tele68.com/v1/txmd5/sessions?cp=R&cl=R&pf=web&at=7e3955a9b92d0a12a675097596748258"
URL_HU = "https://wtx.tele68.com/v1/tx/sessions?cp=R&cl=R&pf=web&at=4a79fe6ffe00c22102db76778b434c50"
URL_CACUOC = "https://lc79.bet"

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
            "pattern": deque(maxlen=50),
            "tam_ly": deque(maxlen=50),
            "rsi": deque(maxlen=50),
            "macd": deque(maxlen=50),
            "bbands": deque(maxlen=50)
        }
    }

du_lieu = {
    "md5": tao_cau_truc_loai(),
    "hu": tao_cau_truc_loai()
}

# ======= LẤY DỮ LIỆU =======
def lay_toan_bo_lich_su(url):
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            data = r.json()
            if 'list' in data and len(data['list']) > 0:
                return data['list']
        except Exception as e:
            if attempt < 2:
                time.sleep(1)
            else:
                logging.error(f"Lỗi lấy dữ liệu từ {url}: {e}")
    return []

# ======= CÁC CHỈ BÁO KỸ THUẬT =======
def tinh_rsi(mang, period=14):
    """Tính RSI (Relative Strength Index)"""
    if len(mang) < period + 1:
        return 50
    
    gains = []
    losses = []
    
    for i in range(1, len(mang)):
        diff = mang[i] - mang[i-1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))
    
    avg_gain = sum(gains[-period:]) / period if len(gains) >= period else sum(gains) / len(gains)
    avg_loss = sum(losses[-period:]) / period if len(losses) >= period else sum(losses) / len(losses)
    
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def tinh_macd(mang, fast=12, slow=26, signal=9):
    """Tính MACD đơn giản"""
    if len(mang) < slow + signal:
        return 0
    
    def ema(data, period):
        if len(data) < period:
            return sum(data) / len(data) if len(data) > 0 else 0
        multiplier = 2 / (period + 1)
        ema_val = sum(data[:period]) / period
        for val in data[period:]:
            ema_val = (val - ema_val) * multiplier + ema_val
        return ema_val
    
    fast_ema = ema(mang, fast)
    slow_ema = ema(mang, slow)
    macd_line = fast_ema - slow_ema
    
    return macd_line

def tinh_bbands(mang, period=20):
    """Tính Bollinger Bands"""
    if len(mang) < period:
        return 50
    
    last_values = mang[-period:]
    mean = statistics.mean(last_values)
    std = statistics.stdev(last_values) if len(last_values) > 1 else 0.1
    
    current = mang[-1]
    if std == 0:
        return 50
    
    upper = mean + 2 * std
    lower = mean - 2 * std
    
    if current >= upper:
        return 100
    elif current <= lower:
        return 0
    else:
        return ((current - lower) / (upper - lower)) * 100

# ======= 9 PHƯƠNG PHÁP PHÂN TÍCH =======
def phan_tich_9_phuong_phap(danh_sach, loai=""):
    """
    9 PHƯƠNG PHÁP PHÂN TÍCH - CẢI TIẾN CHO MD5
    Thêm RSI, MACD, Bollinger Bands
    """
    if not danh_sach or len(danh_sach) < 15:
        return tao_du_doan_mac_dinh(danh_sach, loai)
    
    van_hien_tai = danh_sach[0]
    lich_su = danh_sach[1:]
    
    ket_qua = [p['resultTruyenThong'] for p in lich_su]
    diem = [p['point'] for p in lich_su]
    tong_van = len(ket_qua)
    
    # Chuyển đổi sang số: 1 = TÀI, 0 = XỈU
    mang_so = [1 if k == 'TAI' else 0 for k in ket_qua]
    
    # ============================================================
    # PHƯƠNG PHÁP 1: CHUỖI MARKOV BẬC 3
    # ============================================================
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
    
    # ============================================================
    # PHƯƠNG PHÁP 2: PHÂN TÍCH CHU KỲ
    # ============================================================
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
    
    # ============================================================
    # PHƯƠNG PHÁP 3: MACHINE LEARNING
    # ============================================================
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
    
    # ============================================================
    # PHƯƠNG PHÁP 4: BAYESIAN ĐIỂM SỐ
    # ============================================================
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
    
    # ============================================================
    # PHƯƠNG PHÁP 5: PATTERN MATCHING
    # ============================================================
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
    
    # ============================================================
    # PHƯƠNG PHÁP 6: TÂM LÝ ĐÁM ĐÔNG
    # ============================================================
    def tam_ly_dam_dong_can_bang(mang):
        if len(mang) < 10:
            return 0.5
        
        chuoi_hien_tai = 1
        for i in range(1, len(mang)):
            if mang[i] == mang[0]:
                chuoi_hien_tai += 1
            else:
                break
        
        tat_ca_chuoi = []
        chuoi_tam = 1
        for i in range(1, len(mang)):
            if mang[i] == mang[i-1]:
                chuoi_tam += 1
            else:
                tat_ca_chuoi.append(chuoi_tam)
                chuoi_tam = 1
        tat_ca_chuoi.append(chuoi_tam)
        
        dem_dao_chieu = 0
        dem_khong_dao = 0
        vi_tri = 0
        
        for chieu_dai in tat_ca_chuoi[:-1]:
            if chieu_dai >= 4:
                if vi_tri + chieu_dai < len(mang):
                    if mang[vi_tri + chieu_dai] != mang[vi_tri + chieu_dai - 1]:
                        dem_dao_chieu += 1
                    else:
                        dem_khong_dao += 1
            vi_tri += chieu_dai
        
        tong_chuoi_dai = dem_dao_chieu + dem_khong_dao
        if tong_chuoi_dai > 0 and chuoi_hien_tai >= 4:
            ty_le_dao_chieu = dem_dao_chieu / tong_chuoi_dai
            if ty_le_dao_chieu > 0.5:
                return 1 - mang[0]
            else:
                return mang[0]
        
        return 0.5
    
    p_tam_ly = tam_ly_dam_dong_can_bang(mang_so)
    
    # ============================================================
    # PHƯƠNG PHÁP 7: RSI (CHỈ BÁO SỨC MẠNH TƯƠNG ĐỐI)
    # ============================================================
    def phan_tich_rsi(mang):
        """Phân tích RSI - chỉ báo quá mua/quá bán"""
        if len(mang) < 20:
            return 0.5
        
        rsi = tinh_rsi(mang, 14)
        
        if rsi > 70:
            return 0.3  # Nghiêng về XỈU
        elif rsi < 30:
            return 0.7  # Nghiêng về TÀI
        else:
            if rsi > 50:
                return 0.55
            else:
                return 0.45
    
    p_rsi = phan_tich_rsi(mang_so)
    
    # ============================================================
    # PHƯƠNG PHÁP 8: MACD
    # ============================================================
    def phan_tich_macd(mang):
        """Phân tích MACD - xu hướng"""
        if len(mang) < 30:
            return 0.5
        
        macd = tinh_macd(mang, 12, 26, 9)
        
        if macd > 0.05:
            return 0.6
        elif macd < -0.05:
            return 0.4
        else:
            return 0.5
    
    p_macd = phan_tich_macd(mang_so)
    
    # ============================================================
    # PHƯƠNG PHÁP 9: BOLLINGER BANDS
    # ============================================================
    def phan_tich_bbands(mang):
        """Phân tích Bollinger Bands - biến động"""
        if len(mang) < 20:
            return 0.5
        
        bb_pos = tinh_bbands(mang, 20)
        
        if bb_pos > 80:
            return 0.4
        elif bb_pos < 20:
            return 0.6
        else:
            return 0.5
    
    p_bbands = phan_tich_bbands(mang_so)
    
    # ============================================================
    # META-LEARNING (TRỌNG SỐ ĐỘNG)
    # ============================================================
    def tinh_trong_so_dong(loai):
        hieu_suat = du_lieu[loai]['hieu_suat_phuong_phap'] if loai in du_lieu else None
        
        trong_so_mac_dinh = {
            'markov': 0.15,
            'fft': 0.10,
            'ml': 0.15,
            'bayes': 0.10,
            'pattern': 0.10,
            'tam_ly': 0.10,
            'rsi': 0.15,
            'macd': 0.10,
            'bbands': 0.05
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
    
    # ============================================================
    # TỔNG HỢP 9 PHƯƠNG PHÁP
    # ============================================================
    p_tai = (
        p_markov * w.get('markov', 0.15) +
        p_chu_ky * w.get('fft', 0.10) +
        p_ml * w.get('ml', 0.15) +
        p_bayes * w.get('bayes', 0.10) +
        p_pattern * w.get('pattern', 0.10) +
        p_tam_ly * w.get('tam_ly', 0.10) +
        p_rsi * w.get('rsi', 0.15) +
        p_macd * w.get('macd', 0.10) +
        p_bbands * w.get('bbands', 0.05)
    )
    
    p_tai = max(0.05, min(0.95, p_tai))
    p_xiu = 1 - p_tai
    
    # ============================================================
    # QUYẾT ĐỊNH CUỐI CÙNG - TĂNG NGƯỠNG CHO MD5
    # ============================================================
    if loai == 'md5':
        nguong = 0.58
        nguong_can_nhac = 0.52
    else:
        nguong = 0.53
        nguong_can_nhac = 0.50
    
    chenh_lech = abs(p_tai - 0.5)
    do_tin_cay_co_so = min(95, 25 + chenh_lech * 300 + (tong_van / 20))
    
    # Kiểm tra tỉ lệ thắng gần đây cho MD5
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
    
    # ============================================================
    # TẠO PHÂN TÍCH CHI TIẾT
    # ============================================================
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
        ('Markov Bậc 3', p_markov, w.get('markov', 0.15)),
        ('Phân Tích Chu Kỳ', p_chu_ky, w.get('fft', 0.10)),
        ('Machine Learning', p_ml, w.get('ml', 0.15)),
        ('Bayesian Điểm Số', p_bayes, w.get('bayes', 0.10)),
        ('Pattern Matching', p_pattern, w.get('pattern', 0.10)),
        ('Tâm Lý Đám Đông', p_tam_ly, w.get('tam_ly', 0.10)),
        ('RSI (Sức mạnh)', p_rsi, w.get('rsi', 0.15)),
        ('MACD (Xu hướng)', p_macd, w.get('macd', 0.10)),
        ('Bollinger Bands', p_bbands, w.get('bbands', 0.05))
    ]
    
    pp_manh_nhat = max(cac_pp, key=lambda x: abs(x[1] - 0.5))
    
    phan_tich = f"""
PHAN TICH 9 PHUONG PHAP - {loai.upper()}
Du lieu: {tong_van} van

VAN HIEN TAI: {van_hien_tai['resultTruyenThong']} | Diem: {van_hien_tai['point']}
CHUOI: {chuoi_hien_tai} van {van_hien_tai['resultTruyenThong']} lien tiep

------------------------------------------------------------
THONG KE TONG THE:
- TAI: {so_tai} van ({so_tai/tong_van*100:.1f}%)
- XIU: {so_xiu} van ({so_xiu/tong_van*100:.1f}%)
- Chenh lech: {abs(so_tai-so_xiu)} van

------------------------------------------------------------
9 PHUONG PHAP PHAN TICH:
------------------------------------------------------------
"""
    for i, (ten, p, w) in enumerate(cac_pp, 1):
        phan_tich += f"{i}. {ten:<20} (w={w:.0%}): TAI={p*100:.1f}% | XIU={(1-p)*100:.1f}%\n"
    
    phan_tich += f"""
------------------------------------------------------------
KET QUA TONG HOP:
- XAC SUAT TAI: {p_tai*100:.2f}%
- XAC SUAT XIU: {p_xiu*100:.2f}%
- NGUONG QUYET DINH: {nguong*100:.1f}%
- DO TIN CAY: {do_tin_cay_co_so:.0f}%

KHUYEN NGHI: {khuyen} ({do_tin})
"""
    
    return {
        'khuyen_nghi': khuyen,
        'xac_suat_tai': round(p_tai, 4),
        'xac_suat_xiu': round(p_xiu, 4),
        'do_tin_cay': do_tin,
        'do_tin_cay_so': round(do_tin_cay_co_so, 1),
        'phan_tich': phan_tich,
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
        'p_tam_ly': p_tam_ly,
        'p_rsi': p_rsi,
        'p_macd': p_macd,
        'p_bbands': p_bbands,
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
        'phan_tich': f'Dang thu thap du lieu cho {loai}... Can it nhat 15 van.',
        'van_gan_nhat': van_gan,
        'chieu_dai_chuoi': 0,
        'ket_qua_hien_tai': van_gan['resultTruyenThong'] if van_gan else None,
        'tong_so_van': len(danh_sach),
        'so_tai': 0,
        'so_xiu': 0,
        'p_markov': 0.5, 'p_chu_ky': 0.5, 'p_ml': 0.5,
        'p_bayes': 0.5, 'p_pattern': 0.5, 'p_tam_ly': 0.5,
        'p_rsi': 0.5, 'p_macd': 0.5, 'p_bbands': 0.5,
        'trong_so': {'markov':0.15, 'fft':0.10, 'ml':0.15, 'bayes':0.10, 
                     'pattern':0.10, 'tam_ly':0.10, 'rsi':0.15, 'macd':0.10, 'bbands':0.05},
        'nguong': 0.58
    }

# ======= CẬP NHẬT HIỆU SUẤT =======
def cap_nhat_hieu_suat(du_doan, ket_qua_thuc, loai):
    if not du_doan or ket_qua_thuc not in ['TAI', 'XIU']:
        return
    
    ket_qua_so = 1 if ket_qua_thuc == 'TAI' else 0
    hieu_suat = du_lieu[loai]['hieu_suat_phuong_phap']
    
    methods = [
        ('markov', du_doan['p_markov']),
        ('fft', du_doan['p_chu_ky']),
        ('ml', du_doan['p_ml']),
        ('bayes', du_doan['p_bayes']),
        ('pattern', du_doan['p_pattern']),
        ('tam_ly', du_doan['p_tam_ly']),
        ('rsi', du_doan.get('p_rsi', 0.5)),
        ('macd', du_doan.get('p_macd', 0.5)),
        ('bbands', du_doan.get('p_bbands', 0.5))
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
                data['du_doan_van_tiep'] = phan_tich_9_phuong_phap(danh_sach, loai)
                data['lan_cap_nhat_truoc'] = van_id
                data['thoi_gian_cap_nhat'] = datetime.now().strftime('%H:%M:%S')
                
        except Exception as e:
            logging.error(f"Lỗi cập nhật {loai}: {e}")
        
        time.sleep(2)

# ======= KHỞI ĐỘNG THREAD =======
threading.Thread(target=cap_nhat_loai, args=('md5', URL_MD5), daemon=True).start()
threading.Thread(target=cap_nhat_loai, args=('hu', URL_HU), daemon=True).start()

# ======= HTML TEMPLATE =======
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>NEXUS · Tài Xỉu Dual Intelligence</title>
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

.model-grid{display:grid; grid-template-columns:repeat(3,1fr); gap:10px; padding:16px 22px 20px}
@media(max-width:500px){.model-grid{grid-template-columns:1fr 1fr}}
.model-card{
  background:var(--glass-2); border:1px solid var(--border); border-radius:var(--radius-sm);
  padding:12px; position:relative; overflow:hidden; transition:transform .3s, border-color .3s;
}
.model-card:hover{transform:translateY(-2px); border-color:var(--border-strong)}
.model-card::after{content:''; position:absolute; top:0; left:0; width:100%; height:2px; background:var(--accent, var(--blue))}
.model-top{display:flex; justify-content:space-between; align-items:center; margin-bottom:8px}
.model-name{font-size:.7em; font-weight:600; color:var(--text)}
.model-weight{font-size:.58em; color:var(--text-faint); font-family:'JetBrains Mono',monospace}
.model-pct{font-family:'JetBrains Mono',monospace; font-weight:700; font-size:1.1em; line-height:1}
.model-side{font-size:.58em; color:var(--text-faint); margin-top:1px; text-transform:uppercase; letter-spacing:.5px}
.model-bar-track{height:3px; border-radius:3px; background:rgba(255,255,255,.07); margin-top:8px; overflow:hidden}
.model-bar-fill{height:100%; border-radius:3px; transition:width .8s cubic-bezier(.22,1,.36,1)}

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
        <div class="tag">9 phương pháp · MD5 + Hũ</div>
      </div>
    </div>
    <div class="hud">
      <div class="hud-item">
        <span class="hud-label">Cập nhật</span>
        <span class="hud-value mono" id="hud-time">--:--:--</span>
      </div>
      <a href="https://lc79.bet" target="_blank" class="bet-btn">🎲 Đặt Cược</a>
      <div class="live-chip"><span class="live-dot"></span><span class="live-text">LIVE</span></div>
    </div>
  </header>

  <div class="dual-grid" id="dual-grid">
    <!-- MD5 -->
    <div id="md5-container">
      <div class="gcard" style="border-color:rgba(59,158,255,.3)">
        <div class="gcard-head">
          <span class="eyebrow" style="color:var(--blue)">🔷 MD5</span>
          <span class="eyebrow" style="color:var(--text-faint)">9 phương pháp · ngưỡng 58%</span>
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
            <div class="metric-cell"><div class="metric-num" id="md5-m-streak">0</div><div class="metric-lbl">Chuỗi</div></div>
            <div class="metric-cell"><div class="metric-num" id="md5-m-taixiu">0–0</div><div class="metric-lbl">Tài–Xỉu</div></div>
            <div class="metric-cell"><div class="metric-num" id="md5-m-conf">0%</div><div class="metric-lbl">Độ tin cậy</div></div>
            <div class="metric-cell"><div class="metric-num" id="md5-m-rounds">0</div><div class="metric-lbl">Tổng ván</div></div>
          </div>
        </div>
        <div class="model-grid" id="md5-models">
          {% for name in ['Markov','Chu kỳ','ML','Bayesian','Pattern','Tâm lý','RSI','MACD','BBands'] %}
          <div class="model-card" style="--accent:#3b9eff">
            <div class="model-top"><span class="model-name">{{ name }}</span><span class="model-weight">w 0%</span></div>
            <div class="model-pct" style="color:#3b9eff">50%</div>
            <div class="model-side">nghiêng —</div>
            <div class="model-bar-track"><div class="model-bar-fill" style="width:50%; background:#3b9eff"></div></div>
          </div>
          {% endfor %}
        </div>
      </div>
    </div>

    <!-- HŨ -->
    <div id="hu-container">
      <div class="gcard" style="border-color:rgba(255,140,66,.3)">
        <div class="gcard-head">
          <span class="eyebrow" style="color:var(--orange)">🟠 Hũ</span>
          <span class="eyebrow" style="color:var(--text-faint)">7 phương pháp · ngưỡng 53%</span>
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
            <div class="metric-cell"><div class="metric-num" id="hu-m-streak">0</div><div class="metric-lbl">Chuỗi</div></div>
            <div class="metric-cell"><div class="metric-num" id="hu-m-taixiu">0–0</div><div class="metric-lbl">Tài–Xỉu</div></div>
            <div class="metric-cell"><div class="metric-num" id="hu-m-conf">0%</div><div class="metric-lbl">Độ tin cậy</div></div>
            <div class="metric-cell"><div class="metric-num" id="hu-m-rounds">0</div><div class="metric-lbl">Tổng ván</div></div>
          </div>
        </div>
        <div class="model-grid" id="hu-models">
          {% for name in ['Markov','Chu kỳ','ML','Bayesian','Pattern','Tâm lý','RSI','MACD','BBands'] %}
          <div class="model-card" style="--accent:#ff8c42">
            <div class="model-top"><span class="model-name">{{ name }}</span><span class="model-weight">w 0%</span></div>
            <div class="model-pct" style="color:#ff8c42">50%</div>
            <div class="model-side">nghiêng —</div>
            <div class="model-bar-track"><div class="model-bar-fill" style="width:50%; background:#ff8c42"></div></div>
          </div>
          {% endfor %}
        </div>
      </div>
    </div>
  </div>

  <!-- STATISTICS -->
  <div class="gcard" style="margin-bottom:18px">
    <div class="gcard-head">
      <span class="eyebrow">📊 Thống kê tổng hợp</span>
    </div>
    <div class="stats-grid" id="stats-grid">
      <div class="stat-box"><span class="v mono" id="s-md5-winrate" style="color:var(--emerald)">0%</span><span class="l">MD5 Winrate</span></div>
      <div class="stat-box"><span class="v mono" id="s-hu-winrate" style="color:var(--emerald)">0%</span><span class="l">Hũ Winrate</span></div>
      <div class="stat-box"><span class="v mono" id="s-md5-total">0</span><span class="l">MD5 Dự đoán</span></div>
      <div class="stat-box"><span class="v mono" id="s-hu-total">0</span><span class="l">Hũ Dự đoán</span></div>
    </div>
  </div>

  <!-- HISTORY -->
  <div class="gcard">
    <div class="gcard-head">
      <span class="eyebrow">📜 Lịch sử dự đoán</span>
      <span class="eyebrow" style="color:var(--text-faint)" id="hist-count">0 ván</span>
    </div>
    <div class="timeline" id="timeline">
      <div class="empty">
        <svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.4"/><path d="M12 8v4l2.5 1.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
        <span>Đang thu thập dữ liệu...</span>
      </div>
    </div>
  </div>

  <footer class="foot">NEXUS·TX — 9 phương pháp phân tích · Dữ liệu chỉ mang tính tham khảo</footer>
</div>

<script>
const GAUGE_CIRC = 534.07;

function updateType(type, data) {
  if (!data || data.tong_so_van < 15) {
    document.getElementById(type + '-call').textContent = 'Đang thu thập...';
    return;
  }
  
  const prefix = type;
  const isTai = data.khuyen_nghi === 'TAI';
  const isXiu = data.khuyen_nghi === 'XIU';
  const prob = isTai ? data.xac_suat_tai : (isXiu ? data.xac_suat_xiu : 0.5);
  const callColor = isTai ? '#3b9eff' : (isXiu ? '#ff4d6d' : '#ffb454');
  const accentColor = type === 'md5' ? '#3b9eff' : '#ff8c42';
  
  const gauge = document.getElementById(prefix + '-gauge');
  if (gauge) {
    gauge.setAttribute('stroke', callColor);
    gauge.setAttribute('stroke-dashoffset', GAUGE_CIRC * (1 - prob));
  }
  
  const callEl = document.getElementById(prefix + '-call');
  if (callEl) {
    callEl.textContent = data.khuyen_nghi === 'CAN_NHAC' ? '⚠️ CÂN NHẮC' : 
                         data.khuyen_nghi === 'THAN_TRONG' ? '⚡ THẬN TRỌNG' : data.khuyen_nghi;
    callEl.style.color = callColor;
  }
  
  document.getElementById(prefix + '-conf').textContent = data.do_tin_cay_so + '%';
  document.getElementById(prefix + '-pct-tai').textContent = (data.xac_suat_tai * 100).toFixed(1) + '%';
  document.getElementById(prefix + '-pct-xiu').textContent = (data.xac_suat_xiu * 100).toFixed(1) + '%';
  document.getElementById(prefix + '-bar-tai').style.width = (data.xac_suat_tai * 100) + '%';
  document.getElementById(prefix + '-bar-xiu').style.width = (data.xac_suat_xiu * 100) + '%';
  
  document.getElementById(prefix + '-m-streak').textContent = data.chieu_dai_chuoi;
  document.getElementById(prefix + '-m-taixiu').textContent = data.so_tai + '–' + data.so_xiu;
  document.getElementById(prefix + '-m-conf').textContent = data.do_tin_cay_so + '%';
  document.getElementById(prefix + '-m-rounds').textContent = data.tong_so_van;
  document.getElementById(prefix + '-last-result').textContent = data.ket_qua_hien_tai || '—';
  
  const modelKeys = ['p_markov', 'p_chu_ky', 'p_ml', 'p_bayes', 'p_pattern', 'p_tam_ly', 'p_rsi', 'p_macd', 'p_bbands'];
  const weightKeys = ['markov', 'fft', 'ml', 'bayes', 'pattern', 'tam_ly', 'rsi', 'macd', 'bbands'];
  const cards = document.getElementById(prefix + '-models').querySelectorAll('.model-card');
  cards.forEach((card, idx) => {
    if (idx >= modelKeys.length) return;
    const p = data[modelKeys[idx]] || 0.5;
    const w = data.trong_so ? data.trong_so[weightKeys[idx]] : 0.10;
    card.querySelector('.model-pct').textContent = (p * 100).toFixed(1) + '%';
    card.querySelector('.model-pct').style.color = p >= 0.5 ? accentColor : '#ff4d6d';
    card.querySelector('.model-side').textContent = 'nghiêng ' + (p >= 0.5 ? 'TÀI' : 'XỈU');
    card.querySelector('.model-weight').textContent = 'w ' + (w * 100).toFixed(0) + '%';
    card.querySelector('.model-bar-fill').style.width = (p * 100) + '%';
  });
}

function updateStats(data) {
  if (!data) return;
  document.getElementById('s-md5-winrate').textContent = (data.md5?.thong_ke_tong_hop?.ty_le_thang || 0) + '%';
  document.getElementById('s-hu-winrate').textContent = (data.hu?.thong_ke_tong_hop?.ty_le_thang || 0) + '%';
  document.getElementById('s-md5-total').textContent = data.md5?.thong_ke_tong_hop?.tong_du_doan || 0;
  document.getElementById('s-hu-total').textContent = data.hu?.thong_ke_tong_hop?.tong_du_doan || 0;
  
  if (data.md5?.thoi_gian_cap_nhat || data.hu?.thoi_gian_cap_nhat) {
    document.getElementById('hud-time').textContent = data.md5?.thoi_gian_cap_nhat || data.hu?.thoi_gian_cap_nhat || '--:--:--';
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
    const typeLabel = item.loai === 'hu' ? '🟠 HŨ' : '🔷 MD5';
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

async function fetchData() {
  try {
    const res = await fetch('/api/all', {cache:'no-store'});
    if (!res.ok) return;
    const data = await res.json();
    updateType('md5', data.md5?.du_doan_van_tiep);
    updateType('hu', data.hu?.du_doan_van_tiep);
    updateStats(data);
    
    const allHistory = [];
    if (data.md5?.lich_su_dung_sai) {
      data.md5.lich_su_dung_sai.forEach(h => { h.loai = 'md5'; allHistory.push(h); });
    }
    if (data.hu?.lich_su_dung_sai) {
      data.hu.lich_su_dung_sai.forEach(h => { h.loai = 'hu'; allHistory.push(h); });
    }
    allHistory.sort((a,b) => a.thoi_gian.localeCompare(b.thoi_gian));
    renderTimeline(allHistory);
  } catch(e) {}
}

fetchData();
setInterval(fetchData, 3000);
</script>
</body>
</html>
"""

# ======= ROUTES =======
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, du_lieu=du_lieu)

@app.route('/api/du_lieu/<loai>')
def api_du_lieu(loai):
    return jsonify(du_lieu.get(loai, {}).get('du_doan_van_tiep'))

@app.route('/api/all')
def api_all():
    result = {}
    for loai in ['md5', 'hu']:
        data = du_lieu[loai]
        result[loai] = {
            'du_doan_van_tiep': data['du_doan_van_tiep'],
            'van_gan_nhat': data['van_gan_nhat'],
            'thong_ke_tong_hop': data['thong_ke_tong_hop'],
            'thoi_gian_cap_nhat': data['thoi_gian_cap_nhat'],
            'lich_su_dung_sai': list(data['lich_su_dung_sai'])[-30:]
        }
    return jsonify(result)

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(
        host="0.0.0.0",
        port=port,
        threaded=True
    )