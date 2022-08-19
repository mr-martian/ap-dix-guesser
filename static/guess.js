function post(data) {
	console.log('post');
	console.log(data);
	return $.post('callback', data).fail(console.log);
}

function disp_item(blob, method) {
	let ops = new Set();
	let arr = (method == "surf" ? [blob] : blob);
	for (let lu of arr) {
		for (let ana of lu.analyses) {
			ops.add([lu.surface, ana.lemma, ana.tags[0]].join(' '));
		}
	}
	let ret = '<li><ul>';
	ops.forEach(function(op) {
		ret += '<li>'+op+'</li>';
	});
	ret += '</ul></li>';
	return ret;
}

function disp_list(rv) {
	console.log(rv);
	$('#results').html(rv.entries.map(x => disp_item(x, rv.method)).join(''));
}

function load_list() {
	post({
		'a': 'list',
		'c': $('#count').val(),
		'm': $('#method').val(),
		'g': $('#guess-only').val(),
	}).done(disp_list);
}

$(function() {
	$('#analyze').click(function() {
		post({'a': 'process', 't': $('#text').val()}).done(load_list);
		$('#text').val('');
	});

	$('#count, #method, #guess-only').change(load_list);
});
