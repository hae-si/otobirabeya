function nmi(a,b){
 const ids=Object.keys(a).filter(id=>a[id]!=null&&b[id]!=null),n=ids.length;if(!n)return null;
 const rows=new Map(),cols=new Map(),cells=new Map();
 const add=(m,k)=>m.set(k,(m.get(k)||0)+1);
 for(const id of ids){add(rows,a[id]);add(cols,b[id]);add(cells,JSON.stringify([a[id],b[id]]));}
 const entropy=m=>-[...m.values()].reduce((s,c)=>s+c/n*Math.log(c/n),0);
 let mi=0;for(const [key,c] of cells){const [x,y]=JSON.parse(key);mi+=c/n*Math.log(c*n/(rows.get(x)*cols.get(y)));}
 const den=entropy(rows)+entropy(cols);return den?2*mi/den:1;
}
module.exports={nmi};
