//CHANGE PROJECTS DROPDOWN
var prj_dropdown = document.getElementById('project-dropdown')

for (let i in prj_list){
  prj_dropdown.innerHTML += "<li><a class=\"dropdown-item\" href=\"#proj" + i + "\">" + prj_list[i] + "</a></li>"
}

//CHANGE STATS
var h4_num_prj = document.getElementById('h4-num-prj')
h4_num_prj.innerHTML = parseInt(num_projects) + " ecoEDA projects"

var p_num_prj = document.getElementById('p-num-prj')
p_num_prj.innerHTML = "You've used ecoEDA and reused components for "+ parseInt(num_projects) + " of your EDA projects."

var h4_num_cmpnts = document.getElementById('h4-num-cmpnts')
h4_num_cmpnts.innerHTML = parseInt(components_reused) + " ecoEDA components reused"

var p_num_cmpnts = document.getElementById('p-num-cmpnts')
p_num_cmpnts.innerHTML = "You've opted to reuse an ecoEDA component over buying a new one "+ parseInt(components_reused) + " times."

var h4_lib_cmpnts = document.getElementById('h4-lib-cmpnts')
h4_lib_cmpnts.innerHTML = parseInt(components_in_lib) + " components in library"

var p_lib_cmpnts = document.getElementById('p-lib-cmpnts')
p_lib_cmpnts.innerHTML = "You've added "+ parseInt(components_in_lib) + " different components from devices into your ecoEDA library."

// CHANGE PROJECTS
var charts = {}
var chart_canvases = {}
var chart_data = {}
var chart_config = {}
var prj_container = document.getElementById('prj-container')


for (let i in prj_data) {
  var prj_name = prj_data[i]['Project']

  prj_container.innerHTML += "<div class=\"card mb-4\"><div class=\"card-body pb-5\">" +
                             "<h5 class=\"card-title\" id=\"proj" + i + "\">" + prj_name + "</h5>" +
                             "<br/><h6 class=\"card-subtitle\"> sources from:</h6>" +
                             "<div class=\"container text-center\"><div class=\"row\">" +
                             "<div class=\"col col-5\"><ul class=\"list-group\" id=\"src-list" + i + "\"></ul>" +
                             "</div><div class=\"col col-2\"></div><div class=\"col col-4\">" +
                             "<div class=\"w-75\"><canvas id=\"chart" + i + "\"></canvas>" +
                             "</div></div></div></div></div></div>"

  var src_list = document.getElementById('src-list' + parseInt(i))
  var sources = prj_data[i]['Sources']
  for (let j in sources) {
    src_list.innerHTML += "<li class=\"list-group-item d-flex justify-content-between align-items-center\">" +
                          "<span><i class=\"bi bi-arrow-return-right px-3\"></i>" + j + "</span>" +
                          "<span class=\"badge bg-primary rounded-pill mx-3\">" + parseInt(sources[j]) + " components</span>" +
                          "</li>"
  }
}

//do charts later otherwise won't render properly
for (let i in prj_data){
  var total_components = prj_data[i]['Total Components']
  var ecoEDA_components = prj_data[i]['ecoEDA Components']


  chart_data['chart' + parseInt(i)] = {
    labels: [
      'ecoEDA components',
      'other components'
    ],
    datasets: [{
      label: 'electronic badge dataset',
      data: [ecoEDA_components, total_components-ecoEDA_components],
      backgroundColor: [
        'rgb(173, 230, 158)',
        'rgb(134, 140, 132)'
      ],
      hoverOffset: 4
    }]
  };

  chart_config['chart' + parseInt(i)] = {
    type: 'doughnut',
    data: chart_data['chart' + parseInt(i)],
    options: {}
  };

  chart_canvases['chart' + parseInt(i)] = document.getElementById('chart'+parseInt(i))
  charts['chart' + parseInt(i)] = new Chart(chart_canvases['chart' + parseInt(i)], chart_config['chart' + parseInt(i)])
  console.log(charts['chart' + parseInt(i)])
}
