<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">
    <xsl:output method="html"/>

    <xsl:template match="form">
      <html>
	<head>
	  <style type="text/css">
	    .field {
   	       border: 1px solid black
	    }

	    .title {
	       text-align: center;
	    }

	    .group {
	       width: 100%;
	    }

	    .field-caption {
	       font-size: 60%;
	       font-weight: bold;
	    }

	    .field-content {
	       font-family: Arial, Helvetica, sans-serif;
	    }

	  </style>
	</head>
	<body>
	  <h1 class="title">
	    <xsl:value-of select="title"/>
	  </h1>

	  <table class="group">
	    <tr>
	      <xsl:apply-templates select="field[
					   (@id='number') or 
					   (@id='precedence') or
					   (@id='station') or
					   (@id='place') or
					   (@id='time') or
					   (@id='date')
					   ]"/>
	    </tr>
	  </table>

	  <br/>

	  <table class="group">
	    <tr>
		<xsl:apply-templates select="field[@id='sender']"/>
	    </tr>
	    <tr>
		<xsl:apply-templates select="field[@id='recip']"/>
	    </tr>
	    <tr>
		<xsl:apply-templates select="field[@id='subject']"/>
	    </tr>
	  </table>

	  <br/>

	  <table class="group">
	    <xsl:apply-templates select="field[@id='message']"/>
	  </table>

	</body>
      </html>
</xsl:template>

    <xsl:template match="field">
      <td class="field">
	<span class="field-caption">
		<xsl:value-of select="caption"/>
	</span>
	<br/>
	<span class="field-content">
	  <xsl:choose>
	    <xsl:when test="entry/@type = 'choice'">
	      <xsl:value-of select="entry/choice[@set='y']"/>
	    </xsl:when>
	    <xsl:otherwise>
	      <xsl:value-of select="entry"/>
	    </xsl:otherwise>
	  </xsl:choose>
	</span>
      </td>
    </xsl:template>

      

</xsl:stylesheet>
