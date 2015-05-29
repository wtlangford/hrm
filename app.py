from flask import Flask, Response, render_template
import psycopg2
import psycopg2.extras
import json
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
try:
	from cStringIO import StringIO
except:
	from StringIO import StringIO
app = Flask(__name__)

conn = psycopg2.connect('dbname=db_hrm', cursor_factory=psycopg2.extras.DictCursor)


def secToLabel(s, pos=None):
	if s is None:
		return "0:00"
	return "{:.0f}:{:02.0f}".format (s / 60, s % 60)

@app.route('/users')
def users():
	c = conn.cursor()
	c.execute("""SELECT users.id,username,COUNT(user_id) AS session_count FROM users LEFT JOIN sessions ON user_id=users.id GROUP BY users.id,username ORDER BY users.id""")
	rows = c.fetchall();
	c.close()
	return render_template("users.html",users=rows)

@app.route('/users/<int:user>')
def userInfo(user):
	c = conn.cursor()
	c.execute("""SELECT username from users where id=%s""",[user])
	username = c.fetchone()["username"]
	c.execute("""SELECT id,created::varchar FROM sessions WHERE user_id=%s""",[user])
	rows = c.fetchall()
	c.close()
	return render_template("user.html",username=username,sessions=rows)


@app.route('/')
@app.route('/sessions')
@app.route('/sessions/<int:page>')
def sessions(page=0):
	c = conn.cursor()
	c.execute("""SELECT id,created::varchar FROM sessions ORDER BY created OFFSET %s LIMIT 50""",[page*50])
	session_page = c.fetchall()
	c.close()
	results = []
	for session in session_page:
		stats = sessionStats(session["id"])
		for v in ['duration','zone1','zone2','zone3','zone4']:
			stats[v] = secToLabel(stats[v])
		stats.update(session)
		results.append(stats)
	stats = {}
	if page == 0:
		stats = overallStats()
	return render_template("sessions.html",sessions=results,page=page,globalStats=stats)


@app.route('/sessionGraph/<int:session>')
def sessionGraph(session):
	points = sessionData(session)
	plt.xlabel("Time (s)")
	plt.ylabel("Heart Rate (bpm)")
	for segment in points:
		plt.plot((segment[0],segment[0]+segment[1]),(segment[2],segment[2]),color='green')
	ram = StringIO()
	fig = plt.gcf()
	ax = plt.gca()
	ax.xaxis.set_major_formatter(FuncFormatter(secToLabel))
	fig.set_size_inches(10,3)
	plt.savefig(ram,format="png",dpi=100,bbox_inches='tight')
	return Response(ram.getvalue(),mimetype="image/png")


def overallStats():
	c = conn.cursor()
	c.execute("""
	SELECT MIN(bpm) as min_bpm, MAX(bpm) as max_bpm, SUM(bpm*duration)/SUM(duration) as avg_bpm FROM hrm_data
	""")
	res = dict(c.fetchone())
	c.close()
	return res

def sessionData(session):
	c = conn.cursor()
	c.execute("""
	SELECT EXTRACT(EPOCH FROM start_time-epoch)::int AS start, duration, bpm
	FROM hrm_data, (SELECT min(start_time) AS epoch FROM hrm_data WHERE session_id = %(id)s) a
	WHERE session_id = %(id)s
	""",{'id':session})
	res = [list(row) for row in c.fetchall()]
	c.close()
	return res

def sessionStats(session):
	c = conn.cursor()
	c.execute("""
	WITH zones AS (SELECT users.* FROM sessions,users
		WHERE sessions.id = %(id)s AND user_id=users.id),
	sess AS (SELECT bpm, duration FROM hrm_data WHERE session_id = %(id)s),
	zone1 AS (SELECT SUM(duration) AS zone1 FROM sess,zones
		WHERE bpm <= zone1_max AND bpm >= zone1_min),
	zone2 AS (SELECT SUM(duration) AS zone2 FROM sess,zones
		WHERE bpm <= zone2_max AND bpm >= zone2_min),
	zone3 AS (SELECT SUM(duration) AS zone3 FROM sess,zones
		WHERE bpm <= zone3_max AND bpm >= zone3_min),
	zone4 AS (SELECT SUM(duration) AS zone4 FROM sess,zones
		WHERE bpm <= zone4_max AND bpm >= zone4_min),
	duration AS (SELECT SUM(duration) AS duration FROM sess),
	stats AS (SELECT MIN(bpm) AS min_bpm, MAX(bpm) AS max_bpm, SUM(bpm*duration)/SUM(duration) as avg_bpm FROM sess)
	SELECT * FROM zone1,zone2,zone3,zone4,stats,duration
	""",{'id':session})
	res = dict(c.fetchone())
	c.close()
	return res

if __name__ == "__main__":
	app.run('0.0.0.0',9001,True)
