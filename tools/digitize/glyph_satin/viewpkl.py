import sys, pickle
from view import render
from geom import PPM
D=pickle.load(open(sys.argv[1]+'.pkl','rb'))
x0,y0,x1,y1=[float(v)*PPM for v in sys.argv[3].split(',')]
sc=float(sys.argv[4]) if len(sys.argv)>4 else 4.0
sat=[s for s in D['satins'] if (s['L'][:,0].mean()>x0 and s['L'][:,0].mean()<x1 and s['L'][:,1].mean()>y0 and s['L'][:,1].mean()<y1)]
render(D['polys'], sat, (x0,y0,x1,y1), sc, sys.argv[2])
