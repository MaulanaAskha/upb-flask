from flask import request, render_template, redirect, url_for, jsonify, flash
from flask_login import login_required, current_user
from flask_wtf.csrf import generate_csrf
from sqlalchemy.exc import IntegrityError
from upb_app.models import Bendungan, Petugas, KinerjaKomponen, KinerjaNilai
from upb_app.forms import AddPetugas, AddKinerjaKomponen
from upb_app import db, admin_only
import datetime

from upb_app.admin import bp


@bp.route('/bendungan/petugas')
@login_required
@admin_only
def petugas_bendungan():
    waduk = Bendungan.query.order_by(Bendungan.nama).all()
    petugas = Petugas.query.filter(Petugas.is_active == '1').order_by(Petugas.id).all()

    data = {}
    for w in waduk:
        data[w.id] = {
            'nama': w.name,
            'petugas': []
        }
    for p in petugas:
        if p.tugas == "Koordinator":
            data[p.bendungan.id]['petugas'].insert(0, p)
        else:
            data[p.bendungan.id]['petugas'].append(p)

    return render_template('petugas/bendungan.html',
                            bendungan=waduk,
                            data=data,
                            csrf=generate_csrf())


@bp.route('/bendungan/petugas/add', methods=['POST'])
@login_required
@admin_only
def petugas_bendungan_add():
    form = AddPetugas()
    if form.validate_on_submit():
        try:
            obj_dict = {
                'nama': form.nama.data,
                'tugas': form.jabatan.data,
                'bendungan_id': int(form.bendungan.data),
                'tgl_lahir': form.tgl_lahir.data or None,
                'alamat': form.alamat.data or None,
                'kab': form.kab.data or None,
                'pendidikan': form.pendidikan.data or None,
                'is_active': '1'
            }
            obj = Petugas(**obj_dict)
            db.session.add(obj)
            db.session.commit()
            flash(f"Petugas berhasil ditambahkan", 'success')
        except Exception as e:
            flash(f"Terjadi kesalahan saat mencoba menyimpan data", 'danger')

    return redirect(url_for('admin.petugas_bendungan'))


@bp.route('/bendungan/petugas/<petugas_id>/del', methods=['POST'])
@login_required
@admin_only
def petugas_bendungan_del(petugas_id):
    obj = Petugas.query.get(petugas_id)
    obj.is_active = '0'
    db.session.commit()

    flash(f"Data petugas berhasil dihapus", 'success')
    return redirect(url_for('admin.petugas_bendungan'))


@bp.route('/bendungan/petugas/delete', methods=['POST'])
@login_required
@admin_only
def petugas_delete():
    pet_id = int(request.values.get('pet_id'))

    petugas = Petugas.query.get(pet_id)
    petugas.is_active = '0'
    db.session.commit()

    return "ok"


@bp.route('/bendungan/petugas/update', methods=['POST'])  # @login_required
def petugas_update():
    pk = request.values.get('pk')
    attr = request.values.get('name')
    val = request.values.get('value')

    row = Petugas.query.get(pk)
    setattr(row, attr, val)
    db.session.commit()

    result = {
        "name": attr,
        "pk": pk,
        "value": val
    }
    return jsonify(result)


@bp.route('/bendungan/petugas/kinerja')
@login_required
@admin_only
def petugas_bendungan_kinerja():
    date = request.values.get('sampling')
    sampling = datetime.datetime.strptime(date, "%Y-%m-%d") if date else datetime.datetime.utcnow()

    waduk = Bendungan.query.order_by(Bendungan.nama).all()
    petugas = Petugas.query.filter(Petugas.is_active == '1').order_by(Petugas.id).all()

    data = {}
    for w in waduk:
        data[w.id] = {
            'bend_id': w.id,
            'nama': w.name,
            'koordinator': None,
            'petugas': {
                'keamanan': [],
                'pemeliharaan': [],
                'operasi': [],
                'pemantauan': []
            },
            'is_empty': True
        }
    for p in petugas:
        data[p.bendungan.id]['is_empty'] = False
        if p.tugas == "Koordinator":
            data[p.bendungan.id]['koordinator'] = p
        else:
            data[p.bendungan.id]['petugas'][p.tugas.lower().strip()].append(p)

    kinerjakomponen = KinerjaKomponen.query.all()
    komponen = {
        'all': [],
        'koordinator': [],
        'operasi': [],
        'pemeliharaan': [],
        'pemantauan': [],
        'keamanan': []
    }
    for k in kinerjakomponen:
        komponen[k.jabatan].append(k)
    badge_color = {
        'Sangat Baik': 'lime',
        'Baik': 'palegreen',
        'Cukup': 'yellow',
        'Kurang': 'orange',
        'Buruk': 'red',
    }

    return render_template('petugas/kinerja.html',
                            bendungan=waduk,
                            data=data,
                            komponen=komponen,
                            csrf=generate_csrf(),
                            sampling=sampling,
                            badge_color=badge_color)


@bp.route('/bendungan/petugas/kinerja/add', methods=['POST'])
@login_required
@admin_only
def petugas_bendungan_kinerja_add():
    data = request.form
    sampling = request.form.get('sampling')  # %Y-%m format
    sampling = datetime.datetime.strptime(f"{sampling}-01", "%Y-%m-%d")
    petugas_id = request.form.get('petugas_id', '')

    if not petugas_id:
        flash(f"Petugas Id tidak ditemukan", 'danger')
        return redirect(url_for('admin.petugas_bendungan_kinerja'))

    for k, v in data.items():
        if 'komponen' not in k:
            continue

        komponen_id = k.split('-')[1]
        komponen = KinerjaKomponen.query.get(int(komponen_id))
        nilai = min(max(0, float(v)), komponen.input_max)
        new_obj = KinerjaNilai(
            sampling=sampling,
            nilai=nilai,
            kinerja_komponen_id=int(komponen_id),
            petugas_id=int(petugas_id)
        )
        db.session.add(new_obj)

    try:
        db.session.commit()
    except IntegrityError:
        flash(f"Penilaian Kinerja Petugas sudah dibuat", 'danger')
        return redirect(url_for('admin.petugas_bendungan_kinerja'))

    flash(f"Penilaian Kinerja Petugas berhasil disimpan", 'success')
    return redirect(url_for('admin.petugas_bendungan_kinerja', sampling=sampling.strftime("%Y-%m-%d")))


@bp.route('/bendungan/petugas/kinerja/update', methods=['POST'])  # @login_required
def petugas_bendungan_kinerja_update():
    pk = request.values.get('pk')
    attr = request.values.get('name')
    val = request.values.get('value')

    row = KinerjaNilai.query.get(pk)
    nilai = min(max(0, float(val)), row.kinerja_komponen.input_max)
    setattr(row, attr, nilai)
    db.session.commit()

    result = {
        "name": attr,
        "pk": pk,
        "value": nilai
    }
    return jsonify(result)


@bp.route('/bendungan/petugas/kinerja/detail')
@login_required
@admin_only
def petugas_bendungan_kinerja_detail():
    petugas_id = request.values.get('petugas_id')
    date = request.values.get('sampling')
    sampling = datetime.datetime.strptime(date, "%Y-%m-%d") if date else datetime.datetime.utcnow()

    if not petugas_id:
        flash(f"Data Petugas tidak ditemukan", 'success')
        return redirect(url_for('admin.petugas_bendungan_kinerja', sampling=sampling.strftime("%Y-%m-%d")))

    petugas = Petugas.query.get(petugas_id)
    kinerja = petugas.get_kinerja(sampling)
    data = {
        'sikap': [],
        'pelayanan': []
    }
    for k in kinerja:
        if k.kinerja_komponen.jabatan == petugas.tugas.lower().strip():
            data['pelayanan'].append(k)
        else:
            data['sikap'].append(k)

    kinerjakomponen = KinerjaKomponen.query.all()
    komponen = {
        'all': [],
        'koordinator': [],
        'operasi': [],
        'pemeliharaan': [],
        'pemantauan': [],
        'keamanan': []
    }
    for k in kinerjakomponen:
        komponen[k.jabatan].append(k)

    return render_template('petugas/petugas.html',
                            petugas=petugas,
                            all_petugas=Petugas.query.order_by(Petugas.bendungan_id).all(),
                            data=data,
                            komponen=komponen,
                            sampling=sampling)


@bp.route('/bendungan/petugas/kinerja/komponen')
@login_required
@admin_only
def petugas_bendungan_komponen():
    tugas = [
        'all',
        'koordinator',
        'operasi',
        'pemeliharaan',
        'pemantauan',
        'keamanan'
    ]
    all_komponen = KinerjaKomponen.query.all()
    komponen = {}
    for t in tugas:
        komponen[t] = []
    for k in all_komponen:
        komponen[k.jabatan].append(k)

    return render_template('petugas/komponen.html',
                            tugas=tugas,
                            komponen=komponen,
                            csrf=generate_csrf())


@bp.route('/bendungan/petugas/kinerja/komponen/add', methods=['POST'])
@login_required
@admin_only
def kinerja_komponen_add():
    form = AddKinerjaKomponen()
    print("Add Kinerja Komponen")

    if form.validate_on_submit():
        new_obj = KinerjaKomponen(
            deskripsi=form.deskripsi.data,
            jabatan=form.jabatan.data,
            nilai_max=form.nilai_max.data,
            input_max=form.input_max.data,
            obj_type=form.obj_type.data
        )
        db.session.add(new_obj)
        db.session.commit()

    flash(f"Komponen kinerja petugas berhasil ditambah", 'success')
    return redirect(url_for('admin.petugas_bendungan_komponen'))
