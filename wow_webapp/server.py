#!/usr/bin/env python
import os
from sqlalchemy import create_engine, text
from flask import Flask, request, render_template, g, redirect, abort, session, flash, url_for
from werkzeug.security import generate_password_hash, check_password_hash

tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
app = Flask(__name__, template_folder=tmpl_dir)
app.secret_key = "super-secret-wow-classic-key"

DATABASEURI = "postgresql://rayden:S00261589@192.168.107.18/Rayden_Project"
engine = create_engine(DATABASEURI)

def current_user():
    return session.get("username")

def reset_new_char():
    session.pop("new_char", None)

@app.before_request
def before_request():
    try:
        g.conn = engine.connect()
    except Exception:
        g.conn = None

@app.teardown_request
def teardown_request(exception):
    try:
        if hasattr(g, "conn") and g.conn is not None:
            g.conn.close()
    except Exception:
        pass

@app.route("/")
def index():
    rows = g.conn.execute(text("""
        SELECT
            pc.character_id,
            pc.name AS char_name,
            pc.level,
            pc.username,
            r.name AS race_name,
            c.name AS class_name,
            f.name AS faction_name
        FROM playercharacter pc
        JOIN race r ON pc.race_id = r.race_id
        JOIN class c ON pc.class_id = c.class_id
        JOIN faction f ON pc.faction_id = f.faction_id
        ORDER BY pc.name;
    """)).fetchall()
    return render_template("index.html", characters=rows, user=current_user())

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        if not username or not password:
            flash("Username and password are required.", "danger")
            return redirect(url_for("signup"))
        existing = g.conn.execute(
            text("SELECT username FROM player WHERE username = :u"),
            {"u": username}
        ).fetchone()
        if existing:
            flash("Username already exists.", "danger")
            return redirect(url_for("signup"))
        pw_hash = generate_password_hash(password)
        g.conn.execute(
            text("INSERT INTO player (username, password_hash) VALUES (:u, :p)"),
            {"u": username, "p": pw_hash}
        )
        g.conn.commit()
        flash("Account created. Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("signup.html", user=current_user())

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        row = g.conn.execute(
            text("SELECT username, password_hash FROM player WHERE username = :u"),
            {"u": username}
        ).fetchone()
        if row and row.password_hash and check_password_hash(row.password_hash, password):
            session["username"] = row.username
            flash(f"Welcome, {row.username}!", "success")
            return redirect(url_for("index"))
        flash("Invalid username or password.", "danger")
        return redirect(url_for("login"))
    return render_template("login.html", user=current_user())

@app.route("/logout")
def logout():
    session.pop("username", None)
    flash("Logged out.", "info")
    return redirect(url_for("index"))

@app.route("/profile")
def profile():
    user = current_user()
    if not user:
        flash("You must be logged in to view your profile.", "warning")
        return redirect(url_for("login"))
    chars = g.conn.execute(text("""
        SELECT
            pc.character_id,
            pc.name AS char_name,
            pc.level,
            r.name AS race_name,
            c.name AS class_name,
            f.name AS faction_name
        FROM playercharacter pc
        JOIN race r ON pc.race_id = r.race_id
        JOIN class c ON pc.class_id = c.class_id
        JOIN faction f ON pc.faction_id = f.faction_id
        WHERE pc.username = :u
        ORDER BY pc.name;
    """), {"u": user}).fetchall()
    return render_template("profile.html", user=user, characters=chars)

@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    results = []
    if query:
        results = g.conn.execute(text("""
            SELECT username
            FROM player
            WHERE username ILIKE :q
            ORDER BY username;
        """), {"q": f"%{query}%"}).fetchall()
    return render_template("search_results.html", query=query, results=results, user=current_user())

@app.route("/user/<username>")
def user_public(username):
    user_row = g.conn.execute(
        text("SELECT username FROM player WHERE username = :u"),
        {"u": username}
    ).fetchone()
    if not user_row:
        abort(404)
    chars = g.conn.execute(text("""
        SELECT
            pc.character_id,
            pc.name AS char_name,
            pc.level,
            r.name AS race_name,
            c.name AS class_name,
            f.name AS faction_name
        FROM playercharacter pc
        JOIN race r ON pc.race_id = r.race_id
        JOIN class c ON pc.class_id = c.class_id
        JOIN faction f ON pc.faction_id = f.faction_id
        WHERE pc.username = :u
        ORDER BY pc.name;
    """), {"u": username}).fetchall()
    return render_template("user_public.html", viewed_user=username, characters=chars, user=current_user())

@app.route("/create")
def create_character():
    user = current_user()
    if not user:
        flash("You must be logged in to create a character.", "warning")
        return redirect(url_for("login"))
    reset_new_char()
    factions = g.conn.execute(text("""
        SELECT faction_id, name
        FROM faction
        WHERE name IN ('Alliance', 'Horde')
        ORDER BY CASE WHEN name='Alliance' THEN 1 ELSE 2 END;
    """)).fetchall()
    return render_template("create_faction.html", user=user, factions=factions)

@app.route("/create/faction", methods=["POST"])
def create_faction_step():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    faction_id = request.form.get("faction_id")
    try:
        faction_id = int(faction_id)
    except Exception:
        flash("Please select a faction.", "danger")
        return redirect(url_for("create_character"))
    row = g.conn.execute(
        text("SELECT faction_id, name FROM faction WHERE faction_id=:fid AND name IN ('Alliance','Horde')"),
        {"fid": faction_id}
    ).fetchone()
    if not row:
        flash("Invalid faction selected.", "danger")
        return redirect(url_for("create_character"))
    session["new_char"] = {"username": user, "faction_id": faction_id}
    return redirect(url_for("create_race_step"))

@app.route("/create/race", methods=["GET", "POST"])
def create_race_step():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    new_char = session.get("new_char")
    if not new_char or "faction_id" not in new_char:
        flash("Please choose a faction first.", "warning")
        return redirect(url_for("create_character"))
    faction_id = new_char["faction_id"]
    faction = g.conn.execute(
        text("SELECT faction_id, name FROM faction WHERE faction_id=:fid"),
        {"fid": faction_id}
    ).fetchone()
    races = g.conn.execute(text("""
        SELECT race_id, name
        FROM race
        WHERE faction_id = :fid
        ORDER BY name;
    """), {"fid": faction_id}).fetchall()
    if request.method == "POST":
        race_id = request.form.get("race_id")
        try:
            race_id = int(race_id)
        except Exception:
            flash("Please select a race.", "danger")
            return redirect(url_for("create_race_step"))
        race_ok = g.conn.execute(text("""
            SELECT race_id FROM race
            WHERE race_id=:rid AND faction_id=:fid
        """), {"rid": race_id, "fid": faction_id}).fetchone()
        if not race_ok:
            flash("That race does not belong to the chosen faction.", "danger")
            return redirect(url_for("create_race_step"))
        new_char["race_id"] = race_id
        session["new_char"] = new_char
        return redirect(url_for("create_class_step"))
    return render_template("create_race.html", user=user, faction=faction, races=races)

@app.route("/create/class", methods=["GET", "POST"])
def create_class_step():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    new_char = session.get("new_char")
    if not new_char or "faction_id" not in new_char or "race_id" not in new_char:
        flash("Please choose faction and race first.", "warning")
        return redirect(url_for("create_character"))
    faction_id = new_char["faction_id"]
    race_id = new_char["race_id"]
    faction = g.conn.execute(text("SELECT faction_id, name FROM faction WHERE faction_id=:fid"), {"fid": faction_id}).fetchone()
    race = g.conn.execute(text("SELECT race_id, name FROM race WHERE race_id=:rid"), {"rid": race_id}).fetchone()
    classes = g.conn.execute(text("""
        SELECT c.class_id, c.name
        FROM class c
        JOIN race_class rc ON rc.class_id = c.class_id
        WHERE rc.race_id = :rid
        ORDER BY c.name;
    """), {"rid": race_id}).fetchall()
    if request.method == "POST":
        class_id = request.form.get("class_id")
        name = request.form.get("name", "").strip()
        if not class_id or not name:
            flash("Please choose a class and a name.", "danger")
            return redirect(url_for("create_class_step"))
        try:
            class_id = int(class_id)
        except Exception:
            flash("Invalid class.", "danger")
            return redirect(url_for("create_class_step"))
        rc_ok = g.conn.execute(text("""
            SELECT 1 FROM race_class
            WHERE race_id=:rid AND class_id=:cid
        """), {"rid": race_id, "cid": class_id}).fetchone()
        if not rc_ok:
            flash("That race cannot be that class in WoW Classic.", "danger")
            return redirect(url_for("create_class_step"))
        row = g.conn.execute(text("""
            INSERT INTO playercharacter (username, name, level, race_id, class_id, faction_id)
            VALUES (:u, :n, 1, :rid, :cid, :fid)
            RETURNING character_id;
        """), {"u": user, "n": name, "rid": race_id, "cid": class_id, "fid": faction_id}).fetchone()
        g.conn.commit()
        reset_new_char()
        flash("Character created!", "success")
        return redirect(url_for("character_detail", character_id=row.character_id))
    return render_template("create_class.html", user=user, faction=faction, race=race, classes=classes)

@app.route("/character/<int:character_id>")
def character_detail(character_id):
    char = g.conn.execute(text("""
        SELECT
            pc.character_id,
            pc.name AS char_name,
            pc.level,
            pc.username,
            r.name AS race_name,
            c.name AS class_name,
            f.name AS faction_name
        FROM playercharacter pc
        JOIN race r ON pc.race_id = r.race_id
        JOIN class c ON pc.class_id = c.class_id
        JOIN faction f ON pc.faction_id = f.faction_id
        WHERE pc.character_id = :cid;
    """), {"cid": character_id}).fetchone()
    if not char:
        abort(404)
    equip_rows = g.conn.execute(text("""
        SELECT ce.slot,
               g.gear_id,
               g.name,
               g.gear_type,
               g.armor_type,
               g.weapon_type
        FROM character_equipment ce
        LEFT JOIN gear g ON ce.gear_id = g.gear_id
        WHERE ce.character_id = :cid
        ORDER BY ce.slot;
    """), {"cid": character_id}).fetchall()
    is_owner = (current_user() == char.username)
    return render_template("character_detail.html", character=char, equipment=equip_rows, is_owner=is_owner, user=current_user())

@app.route("/character/<int:character_id>/level", methods=["POST"])
def character_level(character_id):
    user = current_user()
    if not user:
        abort(403)
    owned = g.conn.execute(text("""
        SELECT 1 FROM playercharacter
        WHERE character_id=:cid AND username=:u
    """), {"cid": character_id, "u": user}).fetchone()
    if not owned:
        abort(403)
    level = request.form.get("level", "").strip()
    try:
        level = int(level)
    except Exception:
        flash("Invalid level.", "danger")
        return redirect(url_for("character_detail", character_id=character_id))
    if level < 1:
        level = 1
    if level > 60:
        level = 60
    g.conn.execute(text("""
        UPDATE playercharacter
        SET level = :lvl
        WHERE character_id = :cid
    """), {"lvl": level, "cid": character_id})
    g.conn.commit()
    flash("Level updated.", "success")
    return redirect(request.referrer or url_for("character_detail", character_id=character_id))

@app.route("/character/<int:character_id>/gear", methods=["GET", "POST"])
def character_gear(character_id):
    char = g.conn.execute(text("""
        SELECT
            pc.character_id,
            pc.name AS char_name,
            pc.level,
            pc.username,
            pc.class_id,
            c.name AS class_name
        FROM playercharacter pc
        JOIN class c ON pc.class_id = c.class_id
        WHERE pc.character_id = :cid;
    """), {"cid": character_id}).fetchone()
    if not char:
        abort(404)
    if current_user() != char.username:
        abort(403)
    slots = ["Head", "Chest", "Legs", "Main Hand", "Two Hand", "Ring", "Trinket"]
    if request.method == "POST":
        g.conn.execute(text("DELETE FROM character_equipment WHERE character_id = :cid"), {"cid": character_id})
        for slot in slots:
            field_name = slot.lower().replace(" ", "_")
            gear_id_str = request.form.get(field_name)
            if gear_id_str:
                try:
                    gid = int(gear_id_str)
                except Exception:
                    continue
                g.conn.execute(text("""
                    INSERT INTO character_equipment (character_id, slot, gear_id)
                    VALUES (:cid, :slot, :gid)
                """), {"cid": character_id, "slot": slot, "gid": gid})
        g.conn.commit()
        flash("Equipment updated.", "success")
        return redirect(url_for("character_detail", character_id=character_id))
    gear_options = {}
    for slot in slots:
        rows = g.conn.execute(text("""
            SELECT gear_id, name
            FROM gear
            WHERE slot = :slot
              AND (class_restriction = 'All'
                   OR class_restriction ILIKE :cname
                   OR class_restriction ILIKE '%' || :cname || '%')
            ORDER BY name;
        """), {"slot": slot, "cname": char.class_name}).fetchall()
        gear_options[slot] = rows
    equipped_rows = g.conn.execute(text("""
        SELECT slot, gear_id
        FROM character_equipment
        WHERE character_id = :cid;
    """), {"cid": character_id}).fetchall()
    equipped = {row.slot: row.gear_id for row in equipped_rows}
    return render_template("character_gear.html", character=char, slots=slots, gear_options=gear_options, equipped=equipped, user=current_user())

@app.route("/character/<int:character_id>/quests", methods=["GET", "POST"])
def character_quests(character_id):
    char = g.conn.execute(text("""
        SELECT character_id, name AS char_name, level, username
        FROM playercharacter
        WHERE character_id = :cid;
    """), {"cid": character_id}).fetchone()
    if not char:
        abort(404)
    is_owner = (current_user() == char.username)

    if request.method == "POST":
        if not is_owner:
            abort(403)

        form_items = request.form.items()
        for k, v in form_items:
            if not k.startswith("status_"):
                continue
            qid = k.split("_", 1)[1]
            try:
                qid = int(qid)
            except Exception:
                continue
            choice = v

            if choice == "not_started":
                g.conn.execute(text("""
                    DELETE FROM playercharacter_quest
                    WHERE character_id=:cid AND quest_id=:qid
                """), {"cid": character_id, "qid": qid})
            elif choice == "in_progress":
                g.conn.execute(text("""
                    INSERT INTO playercharacter_quest (character_id, quest_id, status)
                    VALUES (:cid, :qid, 'In Progress')
                    ON CONFLICT (character_id, quest_id)
                    DO UPDATE SET status = EXCLUDED.status
                """), {"cid": character_id, "qid": qid})
            elif choice == "completed":
                g.conn.execute(text("""
                    INSERT INTO playercharacter_quest (character_id, quest_id, status)
                    VALUES (:cid, :qid, 'Completed')
                    ON CONFLICT (character_id, quest_id)
                    DO UPDATE SET status = EXCLUDED.status
                """), {"cid": character_id, "qid": qid})

        g.conn.commit()
        flash("Quest log updated.", "success")
        return redirect(url_for("character_quests", character_id=character_id, view=request.args.get("view","all"), type=request.args.get("type","")))

    status_rows = g.conn.execute(text("""
        SELECT quest_id, status
        FROM playercharacter_quest
        WHERE character_id = :cid;
    """), {"cid": character_id}).fetchall()
    status_map = {r.quest_id: r.status for r in status_rows}

    quests = g.conn.execute(text("""
        SELECT quest_id, name, level_req, type, reward_item_name, reward
        FROM quest
        ORDER BY COALESCE(level_req,0), name;
    """)).fetchall()

    view = request.args.get("view", "all")
    qtype = request.args.get("type", "").strip()

    def computed_status(qid):
        s = status_map.get(qid)
        if s == "Completed":
            return "completed"
        if s == "In Progress":
            return "in_progress"
        return "not_started"

    filtered = []
    for q in quests:
        st = computed_status(q.quest_id)
        if view == "completed" and st != "completed":
            continue
        if view == "in_progress" and st != "in_progress":
            continue
        if view == "not_started" and st != "not_started":
            continue
        if qtype and (q.type or "").lower() != qtype.lower():
            continue
        filtered.append(q)

    types = g.conn.execute(text("""
        SELECT DISTINCT type
        FROM quest
        WHERE type IS NOT NULL AND type <> ''
        ORDER BY type;
    """)).fetchall()

    return render_template(
        "character_quests.html",
        character=char,
        quests=filtered,
        status_map=status_map,
        computed_status=computed_status,
        is_owner=is_owner,
        view=view,
        qtype=qtype,
        types=types,
        user=current_user()
    )

@app.route("/character/<int:character_id>/delete", methods=["POST"])
def delete_character(character_id):
    user = current_user()
    if not user:
        abort(403)
    owned = g.conn.execute(text("""
        SELECT 1 FROM playercharacter
        WHERE character_id = :cid AND username = :u;
    """), {"cid": character_id, "u": user}).fetchone()
    if not owned:
        abort(403)
    g.conn.execute(text("DELETE FROM playercharacter_quest WHERE character_id=:cid"), {"cid": character_id})
    g.conn.execute(text("DELETE FROM character_equipment WHERE character_id=:cid"), {"cid": character_id})
    g.conn.execute(text("DELETE FROM playercharacter WHERE character_id=:cid"), {"cid": character_id})
    g.conn.commit()
    flash("Character deleted.", "info")
    return redirect(url_for("profile"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8111, debug=True)
