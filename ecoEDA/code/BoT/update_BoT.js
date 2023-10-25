
//TITLE CHANGING FOR PROJECT NAME
var title = document.getElementById('title');
title.innerHTML = 'ecoEDA Bill of Teardowns - ' + BoT_project_name;

//SOURCES IN HEADER, FIRST THREE THEN MORE BUTTON
var nav_sources = document.getElementById('nav-sources');
var more_dropdown;

for (let source in BoT_Sources_List){
  if (source >=3) {
    if (source == 3){
      nav_sources.innerHTML += "<li class=\"nav-item dropdown\"> <a class=\"nav-link dropdown-toggle\" data-toggle=\"dropdown\" href=\"#\" role=\"button\" aria-haspopup=\"true\" aria-expanded=\"false\"> More </a> <div class=\"dropdown-menu\" id=\"more-dropdown\"></div></li>";
      more_dropdown = document.getElementById('more-dropdown');
      more_dropdown.innerHTML += "<a class=\"dropdown-item\" href=\"#source" + source + "\">" + BoT_Sources_List[source] + "</a>"
    }
    else if (source > 3) {
      more_dropdown.innerHTML += "<a class=\"dropdown-item\" href=\"#source" + source + "\">" + BoT_Sources_List[source] + "</a>"
    }
  }
  else {
    nav_sources.innerHTML += "<li class=\"nav-item\"><a href=\"#source" + source + "\" class=\"nav-link\">" + BoT_Sources_List[source] + "</a></li>";
  }
}

//SOURCE CARDS
var sources_container = document.getElementById('sources-container');
var source_card_body;

for (let i in BoT_Sources_Data){
  var source_name = BoT_Sources_Data[i]["Source"]
  var num_components = BoT_Sources_Data[i]["Num Components"]
  var teardown_link = BoT_Sources_Data[i]["Teardown Link"]
  console.log(teardown_link)
  var torn_down;
  if (BoT_Sources_Data[i]["Torn Down"]){
    torn_down = 'yes'
  }
  else {
    torn_down = 'no'
  }
  var index = parseInt(i) + 1

  sources_container.innerHTML += "<div class=\"card mb-4\"><div class=\"card-body\" id=\"source" + index + "-card-body\"></div></div>";
  source_card_body = document.getElementById('source' + index +'-card-body')
  source_card_body.innerHTML += "<h5 class=\"card-title\" style=\"font-size: 2em\" id=\"source" + index + "\">[" + index + "] " + source_name + "</h5>"
  source_card_body.innerHTML += "<ul class=\"list-group list-group-horizontal\"><li class=\"list-group-item\" id=\"source" +index+
   "-num-cmpnts\"># cmpnts from source: " + num_components + "</li><li class=\"list-group-item\" id=\"source" + index +
   "-torn-down\">already torn down: " + torn_down + "</li><li class=\"list-group-item list-group-item-active\" id=\"source" + index +
   "-teardown-link\"> <a href=\"" + teardown_link + "\"> teardown link </a> </li></ul>"
  // FILL OUT COMPONENTS TABLE
  source_card_body.innerHTML += "<br/> <h6 class=\"card-subtitle\"> COMPONENTS </h6>"

  source_card_body.innerHTML += "<table class=\"table table-striped\"><thead><tr><th scope=\"col\">Name</th>" +
                                "<th scope=\"col\">References</th>" + "<th scope=\"col\">Value</th>" +
                                "<th scope=\"col\">Footprint</th>" + "<th scope=\"col\">Quantity</th>" +
                                "<th scope=\"col\">PCB Designator</th>" + "<th scope=\"col\">Notes</th>" +
                                "</tr></thead><tbody id=\"source" + index + "-tbody\"></tbody></table>"

  source_t_body = document.getElementById('source' + index +'-tbody')
  var components_data = BoT_Sources_Data[i]["Components"]

  for (let j in components_data){
    var component_name = components_data[j]['Component Name']
    var references = components_data[j]['References']
    var value = components_data[j]['Value']
    var footprint = components_data[j]['Footprint']
    var quantity = components_data[j]['Quantity']
    var pcb_designator = components_data[j]['PCB Designator']
    var notes = components_data[j]['Notes']

    source_t_body.innerHTML += "<tr><th scope=\"row\">" + component_name + "</th>" +
                               "<td>" + references + "</td>" +
                               "<td>" + value + "~</td>" +
                               "<td>" + footprint +"</td>" +
                               "<td>" + quantity + "</td>" +
                               "<td>" + pcb_designator + "</td>" +
                               "<td>" + notes + "~</td></tr>"
  }
}
