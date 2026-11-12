import networkx as nx

def build_tree(sites,rows):
    g=nx.DiGraph();g.add_node('decision',kind='decision',label='Выбор площадки')
    for s in sites:
        node='site_'+s.site_id;g.add_node(node,kind='site',label=s.site_id,status=s.status);g.add_edge('decision',node)
        scenarios=[r for r in rows if r['site_id']==s.site_id and r['sample']=='planning']
        if not scenarios:
            leaf=node+'_blocked';g.add_node(leaf,kind='terminal',label=s.status);g.add_edge(node,leaf)
        else:
            for success in [True,False]:
                subset=[r for r in scenarios if r['success']==success];prob=sum(r['probability'] for r in subset)
                leaf=node+('_ok' if success else '_fail')
                cost=sum(r['probability']*r['cost_rub'] for r in subset)/prob if prob else None
                g.add_node(leaf,kind='terminal',label='Успех' if success else 'Нарушение',conditional_cost_rub=cost)
                g.add_edge(node,leaf,probability=prob)
    return nx.node_link_data(g,edges='edges')

def tree_svg(tree):
    from html import escape
    nodes={n['id']:n for n in tree['nodes']};edges=tree['edges']
    sites=[n for n in nodes if nodes[n].get('kind')=='site'];positions={'decision':(550,35)}
    for i,site in enumerate(sites):
        x=100+i*220;positions[site]=(x,135)
        children=[e for e in edges if e['source']==site]
        for k,e in enumerate(children):positions[e['target']]=(x+(k-(len(children)-1)/2)*95,260)
    parts=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1100 340" role="img" aria-label="Дерево выбора площадки">','<rect width="1100" height="340" fill="#f7f9fc"/>']
    for e in edges:
        x,y=positions[e['source']];xx,yy=positions[e['target']]
        parts.append(f'<line x1="{x}" y1="{y+15}" x2="{xx}" y2="{yy-15}" stroke="#a0adbc"/>')
        if 'probability' in e:parts.append(f'<text x="{(x+xx)/2}" y="{(y+yy)/2}" font-size="12" fill="#526478">{e["probability"]:.1%}</text>')
    for name,(x,y) in positions.items():
        label=nodes[name].get('label',name)
        parts.append(f'<rect x="{x-55}" y="{y-17}" width="110" height="34" rx="6" fill="#e6edf6"/><text x="{x}" y="{y+4}" text-anchor="middle" font-family="Arial" font-size="12">{escape(label)}</text>')
    parts.append('<text x="20" y="325" font-family="Arial" font-size="12">Вероятности — плановая модель; ветви агрегированы в успех / нарушение.</text></svg>')
    return ''.join(parts)
