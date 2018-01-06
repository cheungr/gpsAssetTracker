$(function(){
	$('#btnAddTracker').click(function(){
		
		$.ajax({
			url: '/onboard',
			data: $('form').serialize(),
			type: 'POST',
			success: function(response){
				var resParse = $.parseJSON(response)
				if(resParse.error){
					$("#errorNotice").html(resParse.error);
				}
				else{
					$("#onboardForm").html("<h2 align='center'> Tracker Added! </h2> <h2 align='center'><a href='www.google.com'>Go Home</a></h2>");
				}

				console.log(response);
			},
			error: function(error){
				console.log(error);
			}
		});
	});
});