define([
    'knockout',
    'templates/views/components/plugins/certificate-generator-plugin.htm'
], function(ko, template) {

    function ViewModel(params) {
        this.message = ko.observable("Plugin is working");
    }

    if (!ko.components.isRegistered('certificate-generator-plugin')) {
        ko.components.register('certificate-generator-plugin', {
            viewModel: ViewModel,
            template: template
        });
    }

    return ViewModel;
});