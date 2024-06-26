from flask import Blueprint, jsonify, request, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from flask_wtf.csrf import generate_csrf
from upb_app.models import Bendungan, Embung, Users, KegiatanEmbung, Foto, wil_sungai
from upb_app.models import ManualTmaEmbung, ManualDailyEmbung
from upb_app import db
from upb_app import admin_only, role_check_embung
from upb_app.helper import day_range
from sqlalchemy import and_
from telegram import Bot
from upb_app import app
import datetime
import base64
import uuid
import os

import paho.mqtt.client as mqtt

bp = Blueprint('admin', __name__)


@bp.route('/bendungan')
@login_required
@admin_only
def bendungan():
    ''' Home Bendungan '''
    waduk = Bendungan.query.order_by(Bendungan.wil_sungai, Bendungan.id).all()
    bends = {
        '1': {},
        '2': {},
        '3': {}
    }
    count = 1
    for w in waduk:
        bends[w.wil_sungai][count] = w
        count += 1
    return render_template('bendungan/admin.html',
                            bends=bends,
                            wil_sungai=wil_sungai)


@bp.route('/bendungan/update', methods=['POST'])  # @login_required
def bend_update():
    pk = request.values.get('pk')
    attr = request.values.get('name')
    val = request.values.get('value')
    row = Bendungan.query.get(pk)
    setattr(row, attr, val)
    db.session.commit()

    result = {
        "name": attr,
        "pk": pk,
        "value": val
    }
    return jsonify(result)

@bp.route('/embung/home')
@login_required
def embung_home():
    embung = Embung.query.get(current_user.embung_id)
    operasi = ManualTmaEmbung.query.filter(ManualTmaEmbung.embung_id==embung.id).order_by(ManualTmaEmbung.sampling.desc()).limit(15)
    kegiatan = KegiatanEmbung.query.filter(KegiatanEmbung.embung_id==embung.id).order_by(KegiatanEmbung.sampling.desc()).limit(15)
    fotos = Foto.query.filter(Foto.obj_type=='kegiatan_embung', Foto.obj_id.in_([k.id for k in kegiatan]))
    return render_template('embung/home.html', csrf=generate_csrf(), 
                           embung=embung, operasi=operasi, kegiatan=kegiatan, 
                           sampling=datetime.date.today(),
                           foto=fotos)

@bp.route('/embung')
@login_required
@admin_only
def embung():
    ''' Home Embung '''
    embung = Embung.query.order_by(Embung.is_verified.desc(), Embung.wil_sungai, Embung.elevasi.desc()).all()

    results = {
        'Hulu': [],
        'Madiun': [],
        'Hilir': [],
        'Belum Ada': []
    }
    wil_sungai = ['Hulu','Madiun','Hilir', 'Belum Ada']
    for emb in embung:
        wil_id = emb.wil_sungai or 4
        results[wil_sungai[int(wil_id) - 1]].append(emb)

    return render_template('embung/admin.html',
                            results=results)


@bp.route('/embung/update', methods=['POST'])  # @login_required
def emb_update():
    pk = request.values.get('pk')
    attr = request.values.get('name')
    val = request.values.get('value')
    row = Embung.query.get(pk)
    setattr(row, attr, val)
    db.session.commit()

    result = {
        "name": attr,
        "pk": pk,
        "value": val
    }
    return jsonify(result)


@bp.route('/embung/<emb_id>/verify', methods=['POST'])  # @login_required
def embung_verify(emb_id):
    password = request.values.get('password')

    embung = Embung.query.get(emb_id)
    if embung:
        embung.is_verified = '1'
        username = embung.gen_username()
        user = Users.query.filter(Users.username == username).first()
        if not user:
            new_user = Users(
                username=username,
                role='3',
                embung_id=embung.id
            )
            new_user.set_password(password)

            db.session.add(new_user)
            db.session.flush()
            db.session.commit()
        else:
            user.set_password(password)
            db.session.commit()

            flash(f"Username sudah ada, password updated.", 'success')
            return redirect(url_for('admin.embung'))
        flash(f"Berhasil verifikasi dan tambah user untuk {embung.nama}", 'success')
    else:
        flash(f"Terjadi kesalahan saat mencoba menyimpan data", 'danger')

    return redirect(url_for('admin.embung'))


@bp.route('/embung/harian')
@login_required
@admin_only
def embung_harian():
    ''' Harian Embung '''
    sampling, end = day_range(request.values.get('sampling'))

    embung = Embung.query.filter(Embung.is_verified == '1').order_by(Embung.wil_sungai, Embung.id).all()
    kegiatan = KegiatanEmbung.query.filter(
                                KegiatanEmbung.sampling == sampling.strftime('%Y-%m-%d')
                            ).all()
    all_fotos = Foto.query.filter(Foto.obj_type == "kegiatan_embung", Foto.obj_id.in_([k.id for k in kegiatan])).all()
    fotos = {k.id: {} for k in kegiatan}
    for f in all_fotos:
        length = len(f.keterangan)
        tag = f.keterangan[:length-1]
        fotos[f.obj_id][tag] = f

    embung_a = {
        '1': {},
        '2': {},
        '3': {},
        '4': {}
    }
    embung_b = {
        '1': {},
        '2': {},
        '3': {},
        '4': {}
    }
    wilayah = wil_sungai
    wilayah['4'] = "Lain-Lain"
    count_a = 0
    count_b = 0
    for e in embung:
        if e.jenis == 'a':
            count_a += 1
            embung_a[e.wil_sungai or '4'][e.id] = {
                'embung': e,
                'kegiatan': [],
                'count': count_a
            }
        elif e.jenis == 'b':
            count_b += 1
            embung_b[e.wil_sungai or '4'][e.id] = {
                'embung': e,
                'kegiatan': [],
                'count': count_b
            }
    for keg in kegiatan:
        if keg.embung_id in embung_a[keg.embung.wil_sungai or '4']:
            embung_a[keg.embung.wil_sungai or '4'][keg.embung_id]['kegiatan'].append(keg)
        elif keg.embung_id in embung_b[keg.embung.wil_sungai or '4']:
            embung_b[keg.embung.wil_sungai or '4'][keg.embung_id]['kegiatan'].append(keg)
    return render_template('embung/harian.html',
                            sampling=sampling,
                            wil_sungai=wilayah,
                            embung_a=embung_a,
                            embung_b=embung_b,
                            fotos=fotos)


@bp.route('/showcase/toggle', methods=['POST'])
@login_required
@admin_only
def showcase_toggle():
    foto_id = request.form.get('foto_id')

    foto = Foto.query.get(foto_id)
    if foto.showcase:
        foto.showcase = False
        msg = "hide"
    else:
        foto.showcase = True
        msg = "show"
    db.session.commit()

    return msg


@bp.route('/galeri')
@login_required
@admin_only
def galeri():
    showcased_foto = Foto.query.filter(Foto.showcase).all()

    special = []
    picked_photos = []
    for foto in showcased_foto:
        if not foto.obj_id:
            special.append(foto)
        else:
            picked_photos.append(foto)

    return render_template('about/galeri.html',
                            embung=embung,
                            special=special,
                            picked_photos=picked_photos)


@bp.route('/galery/add', methods=['POST'])
@login_required
@admin_only
def add_galeri():
    latest = Foto.query.order_by(Foto.id.desc()).first()
    raw = request.form.get('foto')
    imageStr = raw.split(',')[1]
    filename = f"galeri_{latest.id}_{request.form.get('filename')}"
    img_file = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    save_file = os.path.join(app.config['SAVE_DIR'], img_file)

    # print(imageStr)
    # print(filename)

    try:
        # convert base64 into image file and then save it
        imgdata = base64.b64decode(imageStr)
        with open(save_file, 'wb') as f:
            f.write(imgdata)

        foto = Foto(
            url=img_file,
            obj_type="gallery",
            showcase=True
        )
        db.session.add(foto)
        db.session.commit()

        return "success"
    except Exception as e:
        print(f"error : {e}")
        return "error"


@bp.route('/gallery/delete', methods=['POST'])
@login_required
@admin_only
def delete_galeri_special():
    foto_id = int(request.values.get('foto_id'))
    print(f"ID Foto : {foto_id}")

    foto = Foto.query.get(foto_id)
    filepath = os.path.join(app.config['SAVE_DIR'], foto.url)

    db.session.delete(foto)
    db.session.commit()

    if os.path.exists(filepath):
        os.remove(filepath)

    return "ok"


@bp.route('/foto/update', methods=["POST"])
@login_required
def foto_update():
    ''' Update Foto '''
    foto_id = request.values.get('foto_id')
    foto_base64 = request.values.get('foto_base64')
    redirect_url = request.values.get('redirect_url')

    foto = Foto.query.get(int(foto_id))

    if foto:
        imageStr = foto_base64.split(',')[1]
        f_ext = foto_base64.split(':')[1].split('/')[1].split(';')[0]

        filename = foto.url.split("/")[-1]
        new_filename = "_".join(filename.split("_")[:-1]) + f"_{str(uuid.uuid4())}.{f_ext}"
        img_file = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
        save_file = os.path.join(app.config['SAVE_DIR'], img_file)

        # convert base64 into image file and then save it
        imgdata = base64.b64decode(imageStr)
        with open(save_file, 'wb') as f:
            f.write(imgdata)

        # delete the old file
        old_file = os.path.join(app.config['SAVE_DIR'], foto.url)
        if os.path.exists(old_file):
            os.remove(old_file)

        foto.url = img_file
        db.session.commit()

        flash('Foto berhasil di update !', 'success')
    else:
        flash('Foto tidak ditemukan !', 'danger')

    return redirect(redirect_url)


@bp.route('/alert/button')
@login_required
@admin_only
def alert_button():
    ''' Return html with button to trigger alert notice '''
    return render_template('operasi/alert.html')


@bp.route('/alert/test')
@login_required
@admin_only
def alert_test():
    ''' Return html with button to trigger alert notice '''
    MQTT_HOST = "mqtt.bbws-bsolo.net"
    MQTT_PORT = 14983
    client = mqtt.Client("overseer")

    print("connecting to broker")
    client.connect(MQTT_HOST, port=MQTT_PORT)

    client.loop_start()
    print("sending alert")
    client.publish("alert/test", "ON")
    client.loop_stop()

    # send telegram
    try:
        desa = request.values.get('desa')
        with open('telegram_token.txt', 'r') as openfile:
            token = openfile.read()
        bot = Bot(token=token.strip())
        bot.sendMessage(chat_id='@ewsbbwspj', text=f"*Status AWAS bendungan Logung*\nSirine {desa} dibunyikan.", parse_mode='Markdown')
    except Exception as e:
        print(e)

    return redirect(url_for('admin.alert_button'))


import upb_app.admin.keamanan
import upb_app.admin.kegiatan
import upb_app.admin.kinerja
import upb_app.admin.operasi
import upb_app.admin.piket
import upb_app.admin.petugas
import upb_app.admin.rencana
import upb_app.admin.users
